// manga_ui/hooks/use-chapter-timer.ts
// Умный таймер работы над текущей главой:
// авто-старт при активности, heartbeat раз в 20 сек и авто-пауза после минуты бездействия.

import { useState, useEffect, useCallback, useRef } from "react"
import { getChapterTimerStatus, startChapterTimer, stopChapterTimer, API_BASE_URL, ApiError } from "@/lib/api"

export interface UseChapterTimerReturn {
  isTimerRunning: boolean
  timerSeconds: number
  handleStartTimer: () => Promise<void>
  handleStopTimer: () => Promise<void>
}

// 1 минута бездействия — авто-пауза
const IDLE_TIMEOUT_MS = 60_000
// Как часто подтверждаем активность на бэкенде
const HEARTBEAT_INTERVAL_MS = 20_000
// Троттлинг обработки событий мыши/клавиатуры
const ACTIVITY_THROTTLE_MS = 2_000

export function useChapterTimer(currentChapterId: number | null): UseChapterTimerReturn {
  const [isTimerRunning, setIsTimerRunning] = useState(false)
  const [timerSeconds, setTimerSeconds] = useState(0)

  const isRunningRef = useRef(false)
  const chapterIdRef = useRef<number | null>(currentChapterId)
  const lastActivityTimeRef = useRef<number>(Date.now())
  const lastActivityEventRef = useRef<number>(0)
  const idleTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Поколение сессии: защищает от «воскрешения» таймера запоздавшим heartbeat
  const stopGenerationRef = useRef(0)
  // Ручная пауза (кнопка «Стоп») — в отличие от авто-паузы по бездействию,
  // активность мыши НЕ должна перезапускать таймер.
  const isManuallyPausedRef = useRef(false)
  // Глава удалена на бэкенде — прекращаем heartbeat без спама ошибок.
  const chapterGoneRef = useRef(false)

  chapterIdRef.current = currentChapterId

  const clearIdleTimeout = useCallback(() => {
    if (idleTimeoutRef.current) {
      clearTimeout(idleTimeoutRef.current)
      idleTimeoutRef.current = null
    }
  }, [])

  // Запуск/подтверждение активности (heartbeat) на бэкенде
  const pingTimer = useCallback(async () => {
    const chapterId = chapterIdRef.current
    if (!chapterId || chapterGoneRef.current) return
    const generation = stopGenerationRef.current
    try {
      const res = await startChapterTimer(chapterId)
      if (!res.success) return
      // Если за время запроса таймер успели остановить — не воскрешаем его
      if (generation !== stopGenerationRef.current) return
      isRunningRef.current = res.is_running
      setIsTimerRunning(res.is_running)
      setTimerSeconds(res.total_seconds)
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        // Главу удалили (в т.ч. из другой вкладки): тихо останавливаемся,
        // иначе heartbeat спамит 404 каждые 2 секунды при движении мыши.
        chapterGoneRef.current = true
        isRunningRef.current = false
        setIsTimerRunning(false)
        return
      }
      console.warn("Не удалось отправить heartbeat таймера:", e)
    }
  }, [])

  const scheduleIdleTimeout = useCallback(() => {
    clearIdleTimeout()
    const chapterId = chapterIdRef.current
    if (!chapterId) return
    idleTimeoutRef.current = setTimeout(() => {
      // Минута без действий — мягко останавливаем текущую сессию
      void (async () => {
        const id = chapterIdRef.current
        if (!id || !isRunningRef.current) return
        stopGenerationRef.current += 1
        isRunningRef.current = false
        setIsTimerRunning(false)
        try {
          const res = await stopChapterTimer(id)
          if (res.success) setTimerSeconds(res.total_seconds)
        } catch (e) {
          console.warn("Не удалось остановить таймер по бездействию:", e)
        }
      })()
    }, IDLE_TIMEOUT_MS)
  }, [clearIdleTimeout])

  // Подписка на активность пользователя и авто-старт сессии
  useEffect(() => {
    // Смена главы снимает ручную паузу и признак удалённой главы.
    isManuallyPausedRef.current = false
    chapterGoneRef.current = false

    if (!currentChapterId) {
      clearIdleTimeout()
      isRunningRef.current = false
      setIsTimerRunning(false)
      setTimerSeconds(0)
      return
    }

    let cancelled = false
    const chapterId = currentChapterId
    lastActivityTimeRef.current = Date.now()
    lastActivityEventRef.current = 0

    const reportActivity = () => {
      lastActivityTimeRef.current = Date.now()
      scheduleIdleTimeout()
      // После ручного «Стоп» или удаления главы активность не перезапускает
      // таймер. Авто-пауза по 60с бездействия сюда не относится — там
      // isManuallyPausedRef остаётся false, и таймер сам возобновляется.
      if (isManuallyPausedRef.current || chapterGoneRef.current) return
      if (!isRunningRef.current) {
        void pingTimer()
      }
    }

    const handleActivity = () => {
      const now = Date.now()
      if (now - lastActivityEventRef.current < ACTIVITY_THROTTLE_MS) return
      lastActivityEventRef.current = now
      reportActivity()
    }

    // Синхронизируем состояние с БД (там мог остаться запущенный таймер),
    // затем мягко стартуем сессию при открытии главы.
    getChapterTimerStatus(chapterId)
      .then((res) => {
        if (cancelled || !res.success) return
        isRunningRef.current = res.is_running
        setIsTimerRunning(res.is_running)
        setTimerSeconds(res.total_seconds)
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          chapterGoneRef.current = true
          return
        }
        console.warn("Не удалось получить статус таймера:", e)
      })
      .finally(() => {
        if (!cancelled) reportActivity()
      })

    window.addEventListener("keydown", handleActivity)
    window.addEventListener("mousedown", handleActivity)
    window.addEventListener("wheel", handleActivity, { passive: true })
    window.addEventListener("input", handleActivity)
    window.addEventListener("pointermove", handleActivity, { passive: true })

    // Сообщаем бэкенду об уходе со страницы, чтобы не потерять последние секунды
    const handlePageHide = () => {
      if (!isRunningRef.current) return
      try {
        fetch(`${API_BASE_URL}/api/chapters/${chapterId}/timer/stop`, {
          method: "POST",
          keepalive: true,
        })
      } catch {
        // beforeunload: ошибки отправки игнорируем
      }
    }

    window.addEventListener("beforeunload", handlePageHide)
    window.addEventListener("pagehide", handlePageHide)

    return () => {
      cancelled = true
      stopGenerationRef.current += 1
      clearIdleTimeout()
      window.removeEventListener("keydown", handleActivity)
      window.removeEventListener("mousedown", handleActivity)
      window.removeEventListener("wheel", handleActivity)
      window.removeEventListener("input", handleActivity)
      window.removeEventListener("pointermove", handleActivity)
      window.removeEventListener("beforeunload", handlePageHide)
      window.removeEventListener("pagehide", handlePageHide)

      // При смене главы/размонтировании закрываем сессию старой главы
      if (isRunningRef.current && !chapterGoneRef.current) {
        isRunningRef.current = false
        stopChapterTimer(chapterId).catch((e) => {
          // 404 — главу удалили до остановки таймера, это ожидаемо.
          if (e instanceof ApiError && e.status === 404) return
          console.warn("Не удалось остановить таймер предыдущей главы:", e)
        })
      }
    }
  }, [currentChapterId, clearIdleTimeout, pingTimer, scheduleIdleTimeout])

  // Heartbeat: подтверждаем активность раз в 20 сек, только пока таймер идёт
  useEffect(() => {
    if (!currentChapterId) return
    const interval = setInterval(() => {
      if (!isRunningRef.current) return
      if (Date.now() - lastActivityTimeRef.current >= IDLE_TIMEOUT_MS) return
      void pingTimer()
    }, HEARTBEAT_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [currentChapterId, pingTimer])

  // Локальный тик каждую секунду для плавного отображения времени
  useEffect(() => {
    if (!isTimerRunning) return
    const interval = setInterval(() => {
      setTimerSeconds((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [isTimerRunning])

  const handleStartTimer = useCallback(async () => {
    isManuallyPausedRef.current = false
    chapterGoneRef.current = false
    lastActivityTimeRef.current = Date.now()
    scheduleIdleTimeout()
    await pingTimer()
  }, [pingTimer, scheduleIdleTimeout])

  const handleStopTimer = useCallback(async () => {
    clearIdleTimeout()
    const chapterId = chapterIdRef.current
    stopGenerationRef.current += 1
    // Ручная пауза: движение мыши больше не должно перезапускать таймер.
    isManuallyPausedRef.current = true
    isRunningRef.current = false
    setIsTimerRunning(false)
    if (!chapterId) return
    try {
      const res = await stopChapterTimer(chapterId)
      if (res.success) setTimerSeconds(res.total_seconds)
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        chapterGoneRef.current = true
        return
      }
      console.error("Ошибка остановки таймера:", e)
    }
  }, [clearIdleTimeout])

  return { isTimerRunning, timerSeconds, handleStartTimer, handleStopTimer }
}

// manga_ui/hooks/use-manga-settings.ts
// Глобальные настройки приложения и базовый кегль шрифта текущего тайтла

import { useState, useEffect, useCallback, useRef } from "react"
import type { TitleSettings } from "@/lib/types"
import { getGlobalSettings, updateTitleSettings } from "@/lib/api"

const DEFAULT_GLOBAL_SETTINGS: TitleSettings = {
  ocr_model: "manga-ocr-base",
  auto_oval_bubble: true,
  default_padding: "safe",
  default_hyphenation: true,
  default_stroke: false,
  font_bubble: "v_CCFaceFront",
  font_thought: "v_CCFaceFront",
  font_sfx: "v_Mighty Zeo 2.0",
  show_sfx: false,
  export_format: "png",
}

export interface UseMangaSettingsReturn {
  globalSettings: TitleSettings
  setGlobalSettings: React.Dispatch<React.SetStateAction<TitleSettings>>
  currentTitleId: number | null
  setCurrentTitleId: (titleId: number | null) => void
  titleFontSize: number
  setTitleFontSize: React.Dispatch<React.SetStateAction<number>>
  isApplyingChapterFont: boolean
  setIsApplyingChapterFont: React.Dispatch<React.SetStateAction<boolean>>
  handleTitleFontSizeChange: (newSize: number) => void
  handleTitleSelected: (titleId: number, defaultFontSize?: number) => void
}

export function useMangaSettings(): UseMangaSettingsReturn {
  // Базовый размер шрифта для текущего тайтла
  const [currentTitleId, setCurrentTitleId] = useState<number | null>(null)
  const [titleFontSize, setTitleFontSize] = useState<number>(14)
  const [isApplyingChapterFont, setIsApplyingChapterFont] = useState(false)

  // Глобальные настройки приложения
  const [globalSettings, setGlobalSettings] = useState<TitleSettings>(DEFAULT_GLOBAL_SETTINGS)

  useEffect(() => {
    async function loadSettings() {
      try {
        const res = await getGlobalSettings()
        if (res.success && res.settings) {
          setGlobalSettings(res.settings)
        }
      } catch (err) {
        console.warn("Не удалось загрузить глобальные настройки:", err)
      }
    }
    loadSettings()
  }, [])

  // Debounce сохранения кегля: быстрые клики +/- не должны слать серию
  // параллельных PUT, ответы которых могут прийти не по порядку.
  const fontSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fontSaveSeqRef = useRef(0)

  useEffect(() => {
    return () => {
      if (fontSaveTimerRef.current) clearTimeout(fontSaveTimerRef.current)
    }
  }, [])

  const handleTitleFontSizeChange = useCallback((newSize: number) => {
    // Оптимистичное локальное обновление — UI реагирует мгновенно.
    setTitleFontSize(newSize)
    const titleId = currentTitleId
    if (!titleId) return

    if (fontSaveTimerRef.current) clearTimeout(fontSaveTimerRef.current)
    fontSaveTimerRef.current = setTimeout(() => {
      fontSaveTimerRef.current = null
      const seq = ++fontSaveSeqRef.current
      updateTitleSettings(titleId, { default_font_size: newSize } as any)
        .then(() => {
          // Устаревший ответ игнорируем: актуальное значение уже отправлено.
          if (seq !== fontSaveSeqRef.current) return
        })
        .catch((err) => {
          console.warn("Не удалось сохранить размер шрифта тайтла:", err)
        })
    }, 400)
  }, [currentTitleId])

  const handleTitleSelected = useCallback((titleId: number, defaultFontSize?: number) => {
    setCurrentTitleId(titleId)
    if (defaultFontSize) {
      setTitleFontSize(defaultFontSize)
    }
  }, [])

  return {
    globalSettings,
    setGlobalSettings,
    currentTitleId,
    setCurrentTitleId,
    titleFontSize,
    setTitleFontSize,
    isApplyingChapterFont,
    setIsApplyingChapterFont,
    handleTitleFontSizeChange,
    handleTitleSelected,
  }
}

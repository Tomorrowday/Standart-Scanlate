// manga_ui/hooks/use-page-blocks.ts
/**
 * Хук управления текстовыми блоками страницы (сохранение, редактирование, клин, стек Undo/Redo).
 * CRUD текстовых блоков страницы (сохранение, редактирование, клин, ручное рисование).
 * Стек истории Undo / Redo вынесен в use-blocks-history.ts
 */

import { useState, useRef, useCallback } from "react"
import type { TextBlock, PageItem, PageStatus, TitleSettings } from "@/lib/types"
import { savePageBlocks, toPageBlocksPayload } from "@/lib/api"
import { useBlocksHistory } from "./use-blocks-history"
import {
  addOrUpdateDrawnBlockOp,
  spotCleanBlockOp,
  type BlockCleanAndDrawContext,
} from "./pipelines/block-clean-and-draw"

export interface DrawRect {
  x: number
  y: number
  width: number
  height: number
  rotation?: number
}

export interface UsePageBlocksReturn {
  textBlocks: TextBlock[]
  setTextBlocks: React.Dispatch<React.SetStateAction<TextBlock[]>>
  textBlocksRef: React.MutableRefObject<TextBlock[]>
  currentPageRef: React.MutableRefObject<PageItem | null>
  selectedId: string | null
  setSelectedId: (id: string | null) => void
  isSaving: boolean
  isDirtyRef: React.MutableRefObject<boolean>
  markDirty: () => void
  isCurrentPage: (pageId: number) => boolean
  applyBlocksForPage: (pageId: number, next: TextBlock[]) => void
  canUndo: boolean
  canRedo: boolean
  undo: () => Promise<void>
  redo: () => void
  recordCleanAction: () => void
  discardLastSnapshot: () => void
  getHistoryDepth: () => number
  truncateHistory: (depth: number) => void
  saveBlocks: (refreshSpeakers?: boolean) => Promise<void>
  saveBlocksExplicit: (targetPageId: number, blocksToSave: TextBlock[], refreshSpeakers?: boolean) => Promise<void>
  setNewPageBlocks: (newBlocks: TextBlock[]) => void
  clearBlocks: () => void
  updateBlock: (id: string, patch: Partial<TextBlock>) => void
  updateBlockTransient: (id: string, patch: Partial<TextBlock>) => void
  deleteBlock: (id: string) => void
  moveBlock: (id: string, direction: "up" | "down") => void
  spotCleanBlock: (block: TextBlock, method?: "auto" | "lama" | "white", deleteAfter?: boolean) => Promise<void>
  addOrUpdateDrawnBlock: (rect: DrawRect, img: HTMLImageElement, existingId?: string, rotation?: number) => Promise<void>
}

// Поля, изменение которых считается «текстовым вводом» и склеивается в один
// шаг Undo, пока пользователь печатает без паузы.
const TEXT_PATCH_KEYS = new Set(["rusText", "japText", "speaker", "status"])
const TEXT_UNDO_COALESCE_MS = 1000

export function usePageBlocks(
  currentPage: PageItem | null,
  globalSettings: TitleSettings,
  onPageStatusUpdate: (pageId: number, status: PageStatus, cleanPath?: string) => void,
  onRefreshSpeakers: (pageId: number) => void
): UsePageBlocksReturn {
  const [textBlocks, setTextBlocks] = useState<TextBlock[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const textBlocksRef = useRef<TextBlock[]>([])
  textBlocksRef.current = textBlocks
  const selectedIdRef = useRef<string | null>(null)
  selectedIdRef.current = selectedId
  const currentPageRef = useRef<PageItem | null>(null)
  currentPageRef.current = currentPage

  const isDirtyRef = useRef(false)
  // Счётчик ревизий правок: позволяет не сбрасывать флаг «грязно», если
  // пользователь продолжил печатать, пока шёл HTTP-запрос сохранения.
  const dirtyVersionRef = useRef(0)

  const markDirty = useCallback(() => {
    dirtyVersionRef.current += 1
    isDirtyRef.current = true
  }, [])

  // Фоновый авто-OCR меняет japText, но это не «правка пользователя»:
  // помечаем страницу грязной без инкремента ревизии, чтобы сохранение,
  // дождавшееся OCR, корректно сбрасывало isDirtyRef.
  const markOcrDirty = useCallback(() => {
    isDirtyRef.current = true
  }, [])

  // Стабильные помощники для пайплайнов с долгими await: обновлять UI
  // разрешено только для той страницы, которая всё ещё открыта.
  const isCurrentPage = useCallback(
    (pageId: number) => currentPageRef.current?.id === pageId,
    []
  )

  const applyBlocksForPage = useCallback((pageId: number, next: TextBlock[]) => {
    if (currentPageRef.current?.id !== pageId) return
    setTextBlocks(next)
    textBlocksRef.current = next
  }, [])

  // Авто-OCR новых баблов выполняется асинхронно и обновляет блок, которого
  // ещё нет в БД. Держим промисы, чтобы сохранение дождалось распознанного
  // текста и не записало пустой jap_text.
  const pendingOcrPromisesRef = useRef<Set<Promise<unknown>>>(new Set())

  // Последнее текстовое изменение: пока пользователь печатает без паузы
  // дольше TEXT_UNDO_COALESCE_MS, новые снапшоты Undo не создаются.
  const lastTextUndoRef = useRef<{ blockId: string; time: number } | null>(null)

  const {
    canUndo,
    canRedo,
    pushUndoSnapshot,
    recordCleanAction,
    undo,
    redo,
    resetHistory,
    discardLastSnapshot,
    getHistoryDepth,
    truncateHistory,
  } = useBlocksHistory({
    textBlocksRef,
    selectedIdRef,
    currentPageRef,
    setTextBlocks,
    setSelectedId,
    markDirty,
    onPageStatusUpdate,
  })

  const saveBlocksExplicit = useCallback(
    async (targetPageId: number, blocksToSave: TextBlock[], refreshSpeakers = true) => {
      const savedVersion = dirtyVersionRef.current
      setIsSaving(true)
      try {
        // Дожидаемся незавершённого авто-OCR: иначе новый блок сохранится в БД
        // с пустым jap_text, а результат распознавания потеряется.
        if (pendingOcrPromisesRef.current.size > 0) {
          await Promise.allSettled(Array.from(pendingOcrPromisesRef.current))
        }

        // Пока ждали OCR, блоки в локальном стейте могли получить japText.
        // Подмешиваем актуальные значения в отправляемый payload.
        const latestBlocks = textBlocksRef.current
        const blocksWithOcr = blocksToSave.map((b) => {
          if (b.japText && b.japText.trim().length > 0) return b
          const latest = latestBlocks.find((lb) => lb.id === b.id)
          if (!latest || !latest.japText || latest.japText.trim().length === 0) return b
          return { ...b, japText: latest.japText, status: latest.status }
        })

        const payload = toPageBlocksPayload(blocksWithOcr)

        const res = await savePageBlocks(targetPageId, payload)
        if (res.page_status) {
          onPageStatusUpdate(targetPageId, res.page_status)
        }

        if (refreshSpeakers) {
          onRefreshSpeakers(targetPageId)
        }

        // Сбрасываем флаг только если сохраняемая страница всё ещё открыта
        // и за время запроса не появилось новых правок.
        if (currentPageRef.current?.id === targetPageId && dirtyVersionRef.current === savedVersion) {
          isDirtyRef.current = false
        }
      } catch (e) {
        console.error("Ошибка сохранения блоков страницы", targetPageId, e)
        throw e
      } finally {
        setIsSaving(false)
      }
    },
    [onPageStatusUpdate, onRefreshSpeakers]
  )

  const saveBlocks = useCallback(
    async (refreshSpeakers = true) => {
      if (!currentPageRef.current) return
      await saveBlocksExplicit(currentPageRef.current.id, textBlocksRef.current, refreshSpeakers)
    },
    [saveBlocksExplicit]
  )

  const setNewPageBlocks = useCallback(
    (newBlocks: TextBlock[]) => {
      const sanitized = newBlocks.map((b) => ({
        ...b,
        fontSize: b.fontSize != null ? Number(b.fontSize) : undefined,
      }))
      setTextBlocks(sanitized)
      textBlocksRef.current = sanitized
      isDirtyRef.current = false
      dirtyVersionRef.current = 0
      lastTextUndoRef.current = null
      resetHistory()
    },
    [resetHistory]
  )

  const clearBlocks = useCallback(() => {
    setTextBlocks([])
    textBlocksRef.current = []
    setSelectedId(null)
    selectedIdRef.current = null
    isDirtyRef.current = false
    dirtyVersionRef.current = 0
    lastTextUndoRef.current = null
    resetHistory()
  }, [resetHistory])

  const updateBlock = useCallback(
    (id: string, patch: Partial<TextBlock>) => {
      // Ранний выход: «чужой» ответ пайплайна не должен создавать Undo-шаг.
      if (!textBlocksRef.current.some((b) => b.id === id)) return

      const patchKeys = Object.keys(patch)
      const isTextOnlyPatch =
        patchKeys.length > 0 && patchKeys.every((key) => TEXT_PATCH_KEYS.has(key))

      const now = Date.now()
      const last = lastTextUndoRef.current
      const shouldCoalesce =
        isTextOnlyPatch &&
        last?.blockId === id &&
        now - last.time < TEXT_UNDO_COALESCE_MS

      if (shouldCoalesce) {
        // Продолжаем ту же «фразу» — новый шаг Undo не нужен.
        lastTextUndoRef.current = { blockId: id, time: now }
      } else {
        pushUndoSnapshot(false)
        lastTextUndoRef.current = isTextOnlyPatch ? { blockId: id, time: now } : null
      }

      markDirty()
      setTextBlocks((prev) => {
        const next = prev.map((b) => {
          if (b.id !== id) return b
          const updated = { ...b, ...patch }
          if (patch.fontSize === null) {
            updated.fontSize = undefined
          }
          return updated
        })
        textBlocksRef.current = next
        return next
      })
    },
    [pushUndoSnapshot, markDirty]
  )

  // Транзиентное обновление UI-состояния (например, japOffset): без Undo-шага
  // и без пометки страницы грязной — смещение намеренно не сохраняется в БД.
  const updateBlockTransient = useCallback(
    (id: string, patch: Partial<TextBlock>) => {
      if (!textBlocksRef.current.some((b) => b.id === id)) return
      setTextBlocks((prev) => {
        const next = prev.map((b) => {
          if (b.id !== id) return b
          const updated = { ...b, ...patch }
          if (patch.fontSize === null) {
            updated.fontSize = undefined
          }
          return updated
        })
        textBlocksRef.current = next
        return next
      })
    },
    []
  )

  const deleteBlock = useCallback(
    (id: string) => {
      if (!textBlocksRef.current.some((b) => b.id === id)) return
      pushUndoSnapshot(false)
      lastTextUndoRef.current = null
      markDirty()
      setTextBlocks((prev) => {
        const idx = prev.findIndex((b) => b.id === id)
        const filtered = prev.filter((b) => b.id !== id)
        const updated = filtered.map((b, i) => ({ ...b, orderIndex: i + 1 }))
        textBlocksRef.current = updated

        setSelectedId((cur) => {
          if (cur !== id) return cur
          if (updated.length === 0) {
            selectedIdRef.current = null
            return null
          }
          const nextIdx = Math.min(Math.max(0, idx), updated.length - 1)
          const nextSelected = updated[nextIdx].id
          selectedIdRef.current = nextSelected
          return nextSelected
        })

        return updated
      })
    },
    [pushUndoSnapshot, markDirty]
  )

  const moveBlock = useCallback(
    (id: string, direction: "up" | "down") => {
      const currentList = textBlocksRef.current
      const idx = currentList.findIndex((b) => b.id === id)
      if (idx < 0) return
      const swapWith = direction === "up" ? idx - 1 : idx + 1
      if (swapWith < 0 || swapWith >= currentList.length) return

      pushUndoSnapshot(false)
      lastTextUndoRef.current = null
      markDirty()
      setTextBlocks((prev) => {
        const i = prev.findIndex((b) => b.id === id)
        if (i < 0) return prev
        const target = direction === "up" ? i - 1 : i + 1
        if (target < 0 || target >= prev.length) return prev
        const next = [...prev]
        ;[next[i], next[target]] = [next[target], next[i]]
        const reindexed = next.map((b, index) => ({ ...b, orderIndex: index + 1 }))
        textBlocksRef.current = reindexed
        return reindexed
      })
    },
    [pushUndoSnapshot, markDirty]
  )

  // Актуальный контекст для операций клина/рисования: функции ниже остаются
  // стабильными, а свежие пропсы и refs читают из этого объекта.
  const blockOpsCtxRef = useRef<BlockCleanAndDrawContext | null>(null)
  blockOpsCtxRef.current = {
    currentPageRef,
    textBlocksRef,
    selectedIdRef,
    markDirty,
    markOcrDirty,
    lastTextUndoRef,
    pendingOcrPromisesRef,
    setTextBlocks,
    setSelectedId,
    pushUndoSnapshot,
    discardLastSnapshot,
    isCurrentPage,
    onPageStatusUpdate,
    globalSettings,
  }

  const spotCleanBlock = useCallback(
    (block: TextBlock, method: "auto" | "lama" | "white" = "auto", deleteAfter = false) =>
      blockOpsCtxRef.current
        ? spotCleanBlockOp(blockOpsCtxRef.current, block, method, deleteAfter)
        : Promise.resolve(),
    []
  )

  const addOrUpdateDrawnBlock = useCallback(
    (rect: DrawRect, _img: HTMLImageElement, existingId?: string, rotation?: number) =>
      blockOpsCtxRef.current
        ? addOrUpdateDrawnBlockOp(blockOpsCtxRef.current, rect, existingId, rotation)
        : Promise.resolve(),
    []
  )

  // Обрезка истории (Escape в инлайн-редакторе) тоже ломает склейку ввода:
  // следующий символ обязан создать новый шаг Undo.
  const handleTruncateHistory = useCallback(
    (depth: number) => {
      truncateHistory(depth)
      lastTextUndoRef.current = null
    },
    [truncateHistory]
  )

  // После Undo/Redo следующий текстовый ввод обязан создать новый снапшот.
  const handleUndo = useCallback(async () => {
    lastTextUndoRef.current = null
    await undo()
  }, [undo])

  const handleRedo = useCallback(() => {
    lastTextUndoRef.current = null
    redo()
  }, [redo])

  return {
    textBlocks,
    setTextBlocks,
    textBlocksRef,
    currentPageRef,
    selectedId,
    setSelectedId,
    isSaving,
    isDirtyRef,
    markDirty,
    isCurrentPage,
    applyBlocksForPage,
    canUndo,
    canRedo,
    undo: handleUndo,
    redo: handleRedo,
    recordCleanAction,
    discardLastSnapshot,
    getHistoryDepth,
    truncateHistory: handleTruncateHistory,
    saveBlocks,
    saveBlocksExplicit,
    setNewPageBlocks,
    clearBlocks,
    updateBlock,
    updateBlockTransient,
    deleteBlock,
    moveBlock,
    spotCleanBlock,
    addOrUpdateDrawnBlock,
  }
}

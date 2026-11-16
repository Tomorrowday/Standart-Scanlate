// manga_ui/hooks/use-page-blocks_impl.ts
// CRUD текстовых блоков страницы (сохранение, редактирование, клин, ручное рисование)
// Стек истории Undo / Redo вынесен в use-blocks-history.ts

import { useState, useRef, useCallback } from "react"
import type { TextBlock, PageItem, PageStatus, TitleSettings } from "@/lib/types"
import { insertBlockInMangaOrder } from "@/lib/typeset"
import { savePageBlocks, runSpotClean, runOcr } from "@/lib/api"
import { useBlocksHistory } from "./use-blocks-history"
import type { DrawRect, UsePageBlocksReturn } from "./use-page-blocks"

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
  } = useBlocksHistory({
    textBlocksRef,
    selectedIdRef,
    currentPageRef,
    setTextBlocks,
    setSelectedId,
    isDirtyRef,
    onPageStatusUpdate,
  })

  const saveBlocksExplicit = useCallback(
    async (targetPageId: number, blocksToSave: TextBlock[], refreshSpeakers = true) => {
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

        const payload = blocksWithOcr.map((b) => ({
          id: b.id,
          class_id: b.class_id ?? 0,
          x: b.x,
          y: b.y,
          width: b.width,
          height: b.height,
          rotation: b.rotation || 0,
          jap_text: b.japText,
          rus_text: b.rusText,
          speaker: b.speaker || "",
          order_index: b.orderIndex || 0,
          font_size: b.fontSize !== undefined && b.fontSize !== null ? Number(b.fontSize) : undefined,
          font_family: b.fontFamily || "v_CCFaceFront",
          is_bold: Boolean(b.isBold),
          is_italic: Boolean(b.isItalic),
          is_uppercase: Boolean(b.isUppercase),
          has_stroke: Boolean(b.hasStroke),
          text_color: b.textColor || "black",
          shape: b.shape || "rect",
          padding_mode: b.paddingMode || "safe",
          min_hyphens: b.minHyphens !== undefined ? Boolean(b.minHyphens) : true,
          status: b.status,
        }))

        const res = await savePageBlocks(targetPageId, payload)
        if (res.page_status) {
          onPageStatusUpdate(targetPageId, res.page_status)
        }

        if (refreshSpeakers) {
          onRefreshSpeakers(targetPageId)
        }

        isDirtyRef.current = false
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
    lastTextUndoRef.current = null
    resetHistory()
  }, [resetHistory])

  const updateBlock = useCallback(
    (id: string, patch: Partial<TextBlock>) => {
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

      isDirtyRef.current = true
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
    [pushUndoSnapshot]
  )

  const deleteBlock = useCallback(
    (id: string) => {
      pushUndoSnapshot(false)
      lastTextUndoRef.current = null
      isDirtyRef.current = true
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
    [pushUndoSnapshot]
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
      isDirtyRef.current = true
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
    [pushUndoSnapshot]
  )

  const spotCleanBlock = useCallback(
    async (block: TextBlock, method: "auto" | "lama" | "white" = "auto", deleteAfter = false) => {
      if (!currentPageRef.current) return
      try {
        pushUndoSnapshot(true)
        lastTextUndoRef.current = null
        const res = await runSpotClean(
          currentPageRef.current.id,
          {
            x: block.x,
            y: block.y,
            width: block.width,
            height: block.height,
            rotation: block.rotation || 0.0,
            shape: block.shape || "rect",
          },
          method
        )
        if (res.success) {
          onPageStatusUpdate(currentPageRef.current.id, res.page_status || "cleaned", res.clean_path)
          if (deleteAfter) {
            isDirtyRef.current = true
            setTextBlocks((prev) => {
              const idx = prev.findIndex((b) => b.id === block.id)
              const filtered = prev.filter((b) => b.id !== block.id)
              const updated = filtered.map((b, i) => ({ ...b, orderIndex: i + 1 }))
              textBlocksRef.current = updated
              setSelectedId((cur) => {
                if (cur !== block.id) return cur
                if (updated.length === 0) return null
                const nextIdx = Math.min(Math.max(0, idx), updated.length - 1)
                return updated[nextIdx].id
              })
              return updated
            })
          }
        } else {
          discardLastSnapshot()
          alert("Ошибка точечного клина: " + (res.error || "Неизвестная ошибка"))
        }
      } catch (e) {
        discardLastSnapshot()
        alert("Ошибка точечного клина: " + String(e))
      }
    },
    [onPageStatusUpdate, pushUndoSnapshot, discardLastSnapshot]
  )

  const addOrUpdateDrawnBlock = useCallback(
    async (rect: DrawRect, _img: HTMLImageElement, existingId?: string, rotation?: number) => {
      pushUndoSnapshot(false)
      lastTextUndoRef.current = null
      isDirtyRef.current = true
      const rot = rotation !== undefined ? rotation : rect.rotation || 0

      if (existingId) {
        setTextBlocks((prev) => {
          const next = prev.map((b) =>
            b.id === existingId
              ? {
                  ...b,
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height,
                  rotation: rot,
                }
              : b
          )
          textBlocksRef.current = next
          return next
        })
        return
      }

      const defaultFont = globalSettings.font_bubble || "v_CCFaceFront"
      const defaultPadding = globalSettings.default_padding || "safe"
      const defaultHyphens = globalSettings.default_hyphenation !== undefined ? globalSettings.default_hyphenation : true

      const id = crypto.randomUUID()
      const newBlock: TextBlock = {
        id,
        class_id: 0,
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        rotation: rot,
        japText: "",
        rusText: "",
        fontSize: undefined,
        fontFamily: defaultFont,
        textColor: "black",
        shape: "rect",
        paddingMode: defaultPadding,
        minHyphens: defaultHyphens,
        status: "new",
      }

      setTextBlocks((prev) => {
        const next = insertBlockInMangaOrder(prev, newBlock)
        textBlocksRef.current = next
        return next
      })
      setSelectedId(id)
      selectedIdRef.current = id

      // Авто-OCR сразу после рисования бабла. Запускается здесь, а не из
      // useEffect в карточке, — иначе гонка с сохранением/сменой страницы.
      const targetPageId = currentPageRef.current?.id
      if (targetPageId) {
        const ocrPromise: Promise<unknown> = runOcr(
          targetPageId,
          newBlock.x,
          newBlock.y,
          newBlock.width,
          newBlock.height,
          rot,
          id,
          newBlock.class_id ?? 0
        )
          .then((ocrText) => {
            // Если пользователь уже переключил страницу — игнорируем ответ
            if (currentPageRef.current?.id !== targetPageId) return
            // Проверяем, что блок не был удалён пользователем, пока шёл OCR
            if (!textBlocksRef.current.some((b) => b.id === id)) return

            isDirtyRef.current = true
            setTextBlocks((prev) => {
              const next = prev.map((b) => {
                if (b.id !== id) return b
                // Если пользователь уже сам вписал japText вручную — не затираем
                if (b.japText && b.japText.trim().length > 0) return b
                const nextStatus: TextBlock["status"] =
                  b.status === "translated" ? "translated" : "ocr-done"
                return {
                  ...b,
                  japText: ocrText,
                  status: nextStatus,
                }
              })
              textBlocksRef.current = next
              return next
            })
          })
          .catch((err) => {
            console.warn("Авто-OCR нового бабла не удался:", err)
          })
          .finally(() => {
            pendingOcrPromisesRef.current.delete(ocrPromise)
          })

        pendingOcrPromisesRef.current.add(ocrPromise)
      }
    },
    [globalSettings, pushUndoSnapshot]
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
    selectedId,
    setSelectedId,
    isSaving,
    isDirtyRef,
    canUndo,
    canRedo,
    undo: handleUndo,
    redo: handleRedo,
    recordCleanAction,
    discardLastSnapshot,
    saveBlocks,
    saveBlocksExplicit,
    setNewPageBlocks,
    clearBlocks,
    updateBlock,
    deleteBlock,
    moveBlock,
    spotCleanBlock,
    addOrUpdateDrawnBlock,
  }
}

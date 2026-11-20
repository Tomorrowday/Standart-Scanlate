// manga_ui/hooks/pipelines/block-clean-and-draw.ts
// Точечный клин бабла и создание/изменение нарисованного вручную блока
// с фоновым авто-OCR (pendingOcrPromisesRef для ожидания при сохранении)

import type { Dispatch, MutableRefObject, SetStateAction } from "react"
import type { PageItem, PageStatus, TextBlock, TitleSettings } from "@/lib/types"
import { insertBlockInMangaOrder } from "@/lib/typeset"
import { runSpotClean, runOcr } from "@/lib/api"
import type { DrawRect } from "../use-page-blocks"

export interface BlockCleanAndDrawContext {
  currentPageRef: MutableRefObject<PageItem | null>
  textBlocksRef: MutableRefObject<TextBlock[]>
  selectedIdRef: MutableRefObject<string | null>
  /** Помечает страницу грязной и инкрементирует ревизию правок. */
  markDirty: () => void
  /** Помечает страницу грязной БЕЗ новой ревизии (фоновый авто-OCR). */
  markOcrDirty: () => void
  lastTextUndoRef: MutableRefObject<{ blockId: string; time: number } | null>
  pendingOcrPromisesRef: MutableRefObject<Set<Promise<unknown>>>
  setTextBlocks: Dispatch<SetStateAction<TextBlock[]>>
  setSelectedId: Dispatch<SetStateAction<string | null>>
  pushUndoSnapshot: (force?: boolean) => void
  discardLastSnapshot: () => void
  /** Проверяет, что страница всё ещё открыта (защита от гонок переключения). */
  isCurrentPage: (pageId: number) => boolean
  onPageStatusUpdate: (pageId: number, status: PageStatus, cleanPath?: string) => void
  globalSettings: TitleSettings
}

export async function spotCleanBlockOp(
  ctx: BlockCleanAndDrawContext,
  block: TextBlock,
  method: "auto" | "lama" | "white" = "auto",
  deleteAfter = false
): Promise<void> {
  const page = ctx.currentPageRef.current
  if (!page) return
  const targetPageId = page.id
  try {
    ctx.pushUndoSnapshot(true)
    ctx.lastTextUndoRef.current = null
    const res = await runSpotClean(
      targetPageId,
      {
        x: block.x,
        y: block.y,
        width: block.width,
        height: block.height,
        rotation: block.rotation || 0.0,
        shape: block.shape || "rect",
        class_id: block.class_id ?? 0,
      },
      method
    )
    if (res.success) {
      ctx.onPageStatusUpdate(targetPageId, res.page_status || "cleaned", res.clean_path)
      // Удаление блока и правки блоков — только у всё ещё открытой страницы.
      if (deleteAfter && ctx.isCurrentPage(targetPageId)) {
        ctx.markDirty()
        ctx.setTextBlocks((prev) => {
          const idx = prev.findIndex((b) => b.id === block.id)
          const filtered = prev.filter((b) => b.id !== block.id)
          const updated = filtered.map((b, i) => ({ ...b, orderIndex: i + 1 }))
          ctx.textBlocksRef.current = updated
          ctx.setSelectedId((cur) => {
            if (cur !== block.id) return cur
            if (updated.length === 0) return null
            const nextIdx = Math.min(Math.max(0, idx), updated.length - 1)
            return updated[nextIdx].id
          })
          return updated
        })
      }
    } else {
      if (ctx.isCurrentPage(targetPageId)) ctx.discardLastSnapshot()
      alert("Ошибка точечного клина: " + (res.error || "Неизвестная ошибка"))
    }
  } catch (e) {
    if (ctx.isCurrentPage(targetPageId)) ctx.discardLastSnapshot()
    alert("Ошибка точечного клина: " + String(e))
  }
}

export async function addOrUpdateDrawnBlockOp(
  ctx: BlockCleanAndDrawContext,
  rect: DrawRect,
  existingId?: string,
  rotation?: number
): Promise<void> {
  ctx.pushUndoSnapshot(false)
  ctx.lastTextUndoRef.current = null
  ctx.markDirty()
  const rot = rotation !== undefined ? rotation : rect.rotation || 0

  if (existingId) {
    ctx.setTextBlocks((prev) => {
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
      ctx.textBlocksRef.current = next
      return next
    })
    return
  }

  const defaultFont = ctx.globalSettings.font_bubble || "v_CCFaceFront"
  const defaultPadding = ctx.globalSettings.default_padding || "safe"
  const defaultHyphens = ctx.globalSettings.default_hyphenation !== undefined ? ctx.globalSettings.default_hyphenation : true

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

  ctx.setTextBlocks((prev) => {
    const next = insertBlockInMangaOrder(prev, newBlock)
    ctx.textBlocksRef.current = next
    return next
  })
  ctx.setSelectedId(id)
  ctx.selectedIdRef.current = id

  // Авто-OCR сразу после рисования бабла. Запускается здесь, а не из
  // useEffect в карточке, — иначе гонка с сохранением/сменой страницы.
  const targetPageId = ctx.currentPageRef.current?.id
  if (!targetPageId) return

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
      if (ctx.currentPageRef.current?.id !== targetPageId) return
      // Проверяем, что блок не был удалён пользователем, пока шёл OCR
      if (!ctx.textBlocksRef.current.some((b) => b.id === id)) return

      // Авто-OCR — не правка пользователя: не поднимаем ревизию dirty,
      // иначе isDirtyRef остаётся true сразу после сохранения, дождавшегося OCR.
      ctx.markOcrDirty()
      ctx.setTextBlocks((prev) => {
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
        ctx.textBlocksRef.current = next
        return next
      })
    })
    .catch((err) => {
      console.warn("Авто-OCR нового бабла не удался:", err)
    })
    .finally(() => {
      ctx.pendingOcrPromisesRef.current.delete(ocrPromise)
    })

  ctx.pendingOcrPromisesRef.current.add(ocrPromise)
}

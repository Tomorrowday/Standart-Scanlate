// manga_ui/hooks/pipelines/detect-ocr-pipeline.ts
// Авто-детекция баблов и массовое OCR всех рамок страницы

import type { PageStatus, TextBlock } from "@/lib/types"
import { mapDbBlockToTextBlock } from "@/lib/typeset"
import { releaseVram, runOcr, runPageAutoDetect } from "@/lib/api"
import { runConcurrent } from "./concurrent-pool"
import type { PagePipelineContext } from "./types"

export async function executeAutoDetect(ctx: PagePipelineContext): Promise<void> {
  const {
    textBlocks,
    setSelectedId,
    applyBlocksForPage,
    isCurrentPage,
    onPageStatusUpdate,
    setIsDetecting,
  } = ctx
  const currentPage = ctx.currentPage
  if (!currentPage) return

  if (textBlocks.length > 0 || (currentPage.status !== "raw" && currentPage.status !== "new")) {
    const ok = confirm("Пересканировать страницу с нуля? Текущие баблы будут заменены.")
    if (!ok) return
  }

  // Фиксируем целевую страницу: пользователь может переключиться, пока идёт детект.
  const targetPageId = currentPage.id
  setIsDetecting(true)
  try {
    const detectRes = await runPageAutoDetect(
      targetPageId,
      ctx.globalSettings.detect_conf,
      false
    )
    if (detectRes.success === false) {
      throw new Error(detectRes.error || "Ошибка детекции")
    }
    const boxes = detectRes.boxes || []
    // Бэкенд сам решает актуальный статус (detected/raw), не хардкодим.
    const newStatus: PageStatus = (detectRes.page_status as PageStatus) || "detected"

    if (!boxes || boxes.length === 0) {
      applyBlocksForPage(targetPageId, [])
      if (isCurrentPage(targetPageId)) {
        setSelectedId(null)
        alert("Баблы с текстом не найдены.")
      }
      onPageStatusUpdate(targetPageId, newStatus)
      return
    }

    const newBlocks: TextBlock[] = boxes.map((box: any) => {
      const mapped = mapDbBlockToTextBlock(box)
      return {
        ...mapped,
        id: box.id !== undefined && box.id !== null ? mapped.id : crypto.randomUUID(),
        fontFamily: box.font_family || ctx.globalSettings.font_bubble || mapped.fontFamily,
        paddingMode:
          (box.padding_mode as TextBlock["paddingMode"]) ||
          ctx.globalSettings.default_padding ||
          mapped.paddingMode,
        minHyphens:
          box.min_hyphens !== undefined
            ? Boolean(box.min_hyphens)
            : (ctx.globalSettings.default_hyphenation ?? mapped.minHyphens),
      }
    })

    // Бэкенд уже записал блоки в БД; UI обновляем только если страница та же.
    applyBlocksForPage(targetPageId, newBlocks)
    if (isCurrentPage(targetPageId) && newBlocks.length > 0) {
      setSelectedId(newBlocks[0].id)
    }
    onPageStatusUpdate(targetPageId, newStatus)
  } catch (e) {
    console.error(e)
    if (isCurrentPage(targetPageId)) alert("Ошибка при авто-детекции")
  } finally {
    setIsDetecting(false)
  }
}

export async function executeOcrAllBlocks(ctx: PagePipelineContext): Promise<void> {
  const {
    textBlocks,
    saveBlocksExplicit,
    applyBlocksForPage,
    setIsOcrRunning,
  } = ctx
  const currentPage = ctx.currentPage
  if (!currentPage || textBlocks.length === 0) return

  // Фиксируем страницу и снимок блоков до первого долгого await.
  const targetPageId = currentPage.id
  const sourceBlocks = [...textBlocks]
  setIsOcrRunning(true)
  try {
    const failed: TextBlock[] = []

    const ocrResults = await runConcurrent(sourceBlocks, 3, async (b) => {
      try {
        const text = await runOcr(
          targetPageId,
          b.x,
          b.y,
          b.width,
          b.height,
          b.rotation || 0,
          b.id,
          b.class_id ?? 0
        )
        return {
          ...b,
          japText: text,
          status: b.status === "translated" ? ("translated" as const) : ("ocr-done" as const),
        }
      } catch (e) {
        // Ошибка OCR не должна затирать существующий текст бабла.
        console.error("Ошибка OCR блока", b.id, e)
        failed.push(b)
        return b
      }
    })

    const succeeded = ocrResults.length - failed.length
    if (succeeded > 0) {
      applyBlocksForPage(targetPageId, ocrResults)
      await saveBlocksExplicit(targetPageId, ocrResults, true)
    }
    if (failed.length > 0) {
      alert(
        `OCR не удался для ${failed.length} из ${sourceBlocks.length} баблов. ` +
          "Существующий текст этих блоков не изменён."
      )
    }
  } catch (e) {
    console.error("Ошибка OCR всех рамок:", e)
    alert("Ошибка OCR")
  } finally {
    releaseVram()
    setIsOcrRunning(false)
  }
}

// manga_ui/hooks/pipelines/export-fullauto-pipeline.ts
// Экспорт запечённой страницы и полный авто-проход (детекция -> OCR -> клин -> перевод -> экспорт)

import { bakePageBlob, loadImage } from "@/lib/typeset"
import {
  getPageCleanImageUrl,
  getPageImageUrl,
  releaseVram,
  runBatchTranslate,
  runCleanPage,
  runOcr,
  saveTranslatedPage,
} from "@/lib/api"
import { checkOllamaConnection } from "@/lib/api/ollama"
import type { PageStatus } from "@/lib/types"
import { runConcurrent } from "./concurrent-pool"
import type { PagePipelineContext } from "./types"

export async function executeExportPage(ctx: PagePipelineContext): Promise<void> {
  const {
    textBlocksRef,
    globalSettings,
    saveBlocksExplicit,
    isCurrentPage,
    onPageStatusUpdate,
    setIsExporting,
    setIsExportSuccess,
  } = ctx
  const currentPage = ctx.currentPage
  if (!currentPage) return

  const targetPageId = currentPage.id
  // Снимок блоков именно целевой страницы: экспорт адресный и не должен
  // подхватить разметку другой страницы, если пользователь переключился.
  const blocksSnapshot = textBlocksRef.current.map((b) => ({ ...b }))

  setIsExporting(true)
  try {
    await saveBlocksExplicit(targetPageId, blocksSnapshot, true)

    let cleanPath = currentPage.clean_path
    if (!cleanPath) {
      const cleanRes = await runCleanPage(targetPageId, "auto")
      if (cleanRes.success && cleanRes.clean_path) {
        cleanPath = cleanRes.clean_path
        // Не понижаем translated/done, если клин не менял стадию страницы.
        onPageStatusUpdate(targetPageId, (cleanRes.page_status as PageStatus) || "cleaned", cleanPath)
      }
    }

    const baseImgUrl = cleanPath
      ? `${getPageCleanImageUrl(targetPageId)}?t=${Date.now()}`
      : getPageImageUrl(targetPageId)

    const baseImg = await loadImage(baseImgUrl)
    const blob = await bakePageBlob(baseImg, blocksSnapshot, globalSettings.default_font_size || 14)

    if (!blob) throw new Error("Не удалось создать Blob изображения в Canvas")

    const res = await saveTranslatedPage(targetPageId, blob)
    if (res.success) {
      if (isCurrentPage(targetPageId)) setIsExportSuccess(true)
      onPageStatusUpdate(targetPageId, "done")
      setTimeout(() => setIsExportSuccess(false), 2500)
    } else {
      alert("Ошибка запекания: " + (res.error || "Неизвестная ошибка"))
    }
  } catch (e) {
    console.error("Ошибка экспорта:", e)
    alert("Ошибка экспорта: " + String(e))
  } finally {
    setIsExporting(false)
  }
}

export async function executeFullAuto(
  ctx: PagePipelineContext,
  runAutoDetect: () => Promise<void>
): Promise<void> {
  const {
    textBlocks,
    globalSettings,
    saveBlocksExplicit,
    applyBlocksForPage,
    isCurrentPage,
    onPageStatusUpdate,
    setShowTypeset,
    setViewMode,
    setIsFullAuto,
    setIsExportSuccess,
  } = ctx
  const currentPage = ctx.currentPage
  if (!currentPage) return

  // Все шаги адресуем зафиксированной странице.
  const targetPageId = currentPage.id

  setIsFullAuto(true)
  try {
    let currentBlocks = textBlocks.map((b) => ({ ...b }))
    await saveBlocksExplicit(targetPageId, currentBlocks, true)

    let ranAutoDetectNow = false
    if (currentBlocks.length === 0 && (currentPage.status === "raw" || currentPage.status === "new")) {
      ranAutoDetectNow = true
      await runAutoDetect()
      // Пользователь мог переключить страницу — продолжать Full Auto нельзя,
      // иначе следующие шаги затронут уже другую страницу.
      if (!isCurrentPage(targetPageId)) return
      currentBlocks = ctx.textBlocksRef.current.map((b) => ({ ...b }))
    }

    if (currentBlocks.length === 0) {
      // Если только что отработал runAutoDetect, он уже показал alert("Баблы с текстом не найдены.")
      if (!ranAutoDetectNow) {
        alert("Баблы на странице отсутствуют.")
      }
      return
    }

    const neededOcrIndices = currentBlocks
      .map((b, idx) => (!b.japText ? idx : null))
      .filter((idx): idx is number => idx !== null)

    if (neededOcrIndices.length > 0) {
      const ocrFailed: number[] = []
      await runConcurrent(neededOcrIndices, 3, async (idx) => {
        const b = currentBlocks[idx]
        try {
          const ocrText = await runOcr(
            targetPageId,
            b.x,
            b.y,
            b.width,
            b.height,
            b.rotation || 0,
            b.id,
            b.class_id ?? 0
          )
          currentBlocks[idx] = { ...b, japText: ocrText, status: "ocr-done" }
        } catch (e) {
          console.error("Ошибка OCR во время Full Auto", b.id, e)
          ocrFailed.push(idx)
        }
      })

      if (ocrFailed.length < neededOcrIndices.length) {
        applyBlocksForPage(targetPageId, [...currentBlocks])
        await saveBlocksExplicit(targetPageId, currentBlocks, true)
      }
      if (ocrFailed.length > 0) {
        throw new Error(
          `OCR не удался для ${ocrFailed.length} из ${neededOcrIndices.length} баблов. ` +
            "Full Auto остановлен, существующий текст не затёрт."
        )
      }
    }

    const cleanRes = await runCleanPage(targetPageId, "auto")
    if (!cleanRes.success) {
      throw new Error("Ошибка при очистке страницы: " + cleanRes.error)
    }
    if (isCurrentPage(targetPageId)) setViewMode("clean")
    onPageStatusUpdate(targetPageId, (cleanRes.page_status as PageStatus) || "cleaned", cleanRes.clean_path)

    const check = await checkOllamaConnection()
    if (check.ok) {
      const toTranslate = currentBlocks
        .filter((b) => b.japText.trim().length > 0)
        .map((b) => ({
          id: b.id,
          text: b.japText,
          speaker: b.speaker,
          class_id: b.class_id ?? 0,
        }))

      if (toTranslate.length > 0) {
        // Единый путь перевода через бэкенд (выбор модели, глоссарий, чанки).
        const translations = await runBatchTranslate(toTranslate, targetPageId)
        const autoOval = globalSettings.auto_oval_bubble ?? true
        currentBlocks = currentBlocks.map((b) => {
          if (translations[b.id]) {
            const isBubble = (b.class_id ?? 0) === 0
            return {
              ...b,
              rusText: translations[b.id],
              shape: isBubble && autoOval ? "ellipse" : b.shape,
              status: "translated" as const,
            }
          }
          return b
        })
      }
      applyBlocksForPage(targetPageId, [...currentBlocks])
      await saveBlocksExplicit(targetPageId, currentBlocks, true)
    }

    if (isCurrentPage(targetPageId)) setShowTypeset(true)

    const cleanImgUrl = `${getPageCleanImageUrl(targetPageId)}?t=${Date.now()}`
    const cleanImg = await loadImage(cleanImgUrl)
    const blob = await bakePageBlob(cleanImg, currentBlocks, globalSettings.default_font_size || 14)

    if (blob) {
      const saveRes = await saveTranslatedPage(targetPageId, blob)
      if (saveRes.success) {
        if (isCurrentPage(targetPageId)) setIsExportSuccess(true)
        onPageStatusUpdate(targetPageId, "done", cleanRes.clean_path)
        setTimeout(() => setIsExportSuccess(false), 2500)
      }
    }
  } catch (e) {
    console.error(e)
    alert("Ошибка при автоматической обработке: " + String(e))
  } finally {
    releaseVram()
    setIsFullAuto(false)
  }
}

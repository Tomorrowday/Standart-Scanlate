// manga_ui/hooks/pipelines/translate-pipeline.ts
// Локальный перевод через Ollama с дораспознаванием пустых баблов и передачей глоссария и синопсиса тайтла

import { releaseVram, runOcr, runBatchTranslate, getGlossary, getProjectTree } from "@/lib/api"
import { checkOllamaConnection } from "@/lib/api/ollama"
import { runConcurrent } from "./concurrent-pool"
import type { PagePipelineContext } from "./types"

export async function loadTitleTranslationContext(titleId?: number | null): Promise<{
  synopsis: string
  glossary: Array<{ jap?: string; rus: string; context?: string }>
}> {
  if (!titleId) return { synopsis: "", glossary: [] }
  try {
    const [tree, glossaryItems] = await Promise.all([
      getProjectTree(titleId).catch(() => null),
      getGlossary(titleId).catch(() => []),
    ])
    return {
      synopsis: tree?.description || "",
      glossary: (glossaryItems || []).map((g) => ({
        jap: g.jap_word,
        rus: g.rus_word,
        context: g.context,
      })),
    }
  } catch {
    return { synopsis: "", glossary: [] }
  }
}

export async function executeTranslateAll(ctx: PagePipelineContext): Promise<void> {
  const {
    textBlocks,
    globalSettings,
    saveBlocksExplicit,
    applyBlocksForPage,
    isCurrentPage,
    onPageStatusUpdate,
    setShowTypeset,
    setIsBatchTranslating,
  } = ctx
  const currentPage = ctx.currentPage
  if (!currentPage || textBlocks.length === 0) return

  // Фиксируем страницу и снимок блоков до первого долгого await.
  const targetPageId = currentPage.id
  setIsBatchTranslating(true)
  try {
    await saveBlocksExplicit(targetPageId, textBlocks, true)

    const blocksToOcr = textBlocks.map((b) => ({ ...b }))
    const neededOcrIndices = blocksToOcr
      .map((b, idx) => (!b.japText ? idx : null))
      .filter((idx): idx is number => idx !== null)

    if (neededOcrIndices.length > 0) {
      const ocrFailed: number[] = []
      await runConcurrent(neededOcrIndices, 3, async (idx) => {
        const b = blocksToOcr[idx]
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
          blocksToOcr[idx] = { ...b, japText: ocrText, status: "ocr-done" }
        } catch (e) {
          // Не помечаем блок ocr-done и не пишем заглушку в japText.
          console.error("Ошибка OCR перед переводом", b.id, e)
          ocrFailed.push(idx)
        }
      })
      if (ocrFailed.length < neededOcrIndices.length) {
        applyBlocksForPage(targetPageId, [...blocksToOcr])
        await saveBlocksExplicit(targetPageId, blocksToOcr, true)
      }
      if (ocrFailed.length > 0) {
        console.warn(`OCR не удался для ${ocrFailed.length} блоков, они пропущены`)
      }
    }

    const toTranslate = blocksToOcr
      .filter((b) => b.japText.trim().length > 0)
      .map((b) => ({
        id: b.id,
        text: b.japText,
        speaker: b.speaker,
        class_id: b.class_id ?? 0,
      }))

    if (toTranslate.length === 0) return

    const check = await checkOllamaConnection()
    if (!check.ok) {
      alert(
        "Локальная нейросеть Ollama не запущена на http://localhost:11434.\n\n" +
        "Для перевода:\n" +
        "1. Запустите Ollama в командной строке: ollama run qwen2.5\n" +
        "2. Либо используйте кнопку «Export JSON» для перевода через Claude / ChatGPT."
      )
      return
    }

    // Единый путь перевода: бэкенд сам выбирает чат-модель, подгружает
    // глоссарий/синопсис по page_id и переводит чанками. Ошибка бросается
    // исключением — существующие переводы и статус страницы не меняются.
    const translations = await runBatchTranslate(toTranslate, targetPageId)

    const autoOval = globalSettings.auto_oval_bubble ?? true
    let translatedCount = 0
    const updated = blocksToOcr.map((b) => {
      if (translations[b.id]) {
        translatedCount += 1
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

    if (translatedCount === 0) {
      alert("Ollama не вернула перевод (пустой или неразборчивый ответ). Текст баблов не изменён.")
      return
    }

    applyBlocksForPage(targetPageId, updated)
    await saveBlocksExplicit(targetPageId, updated, true)

    if (isCurrentPage(targetPageId)) setShowTypeset(true)
    onPageStatusUpdate(targetPageId, "translated")
  } catch (e) {
    console.error(e)
    alert("Ошибка при локальном переводе: " + String(e))
  } finally {
    releaseVram()
    setIsBatchTranslating(false)
  }
}

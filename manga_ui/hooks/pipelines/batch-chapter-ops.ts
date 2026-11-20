// manga_ui/hooks/pipelines/batch-chapter-ops.ts
// Тяжёлые воркеры пакетных действий главы: экспорт страниц с авто-клином и запеканием,
// экспорт скрипта в папку главы и импорт JSON (бэкенд-диалог или браузерный файл)

import type { PageItem, PageStatus, TextBlock } from "@/lib/types"
import {
  saveTranslatedPage,
  getPageDetails,
  getPageCleanImageUrl,
  getPageImageUrl,
  getPageBlocks,
  exportChapterScriptToFolder,
  uploadChapterScript,
  pickAndImportChapterScript,
  runCleanPage,
} from "@/lib/api"
import { loadImage, bakePageBlob, mapDbBlockToTextBlock } from "@/lib/typeset"
import type {
  BatchChapterActionsProps,
  BatchAction,
  BatchProgress,
} from "@/components/batch-chapter-actions"

export interface BatchChapterOpsContext {
  pages: PageItem[]
  chapterId?: number
  titleDefaultFontSize: number
  ensureCurrentPageSaved: () => Promise<void>
  setProgress: (progress: BatchProgress | null) => void
  setJustFinished: (action: BatchAction | null) => void
  fileInputRef: { current: HTMLInputElement | null }
  onPageStatusUpdate?: BatchChapterActionsProps["onPageStatusUpdate"]
  onCompleteBatch?: () => void
  onRefreshCurrent: (action?: BatchAction) => void
}

/** Экспорт одной страницы: при необходимости авто-клин, затем запекание PNG и сохранение. */
export async function exportBakePageOp(ctx: BatchChapterOpsContext, page: PageItem): Promise<void> {
  // Не трогаем undo-бэкапы клина: экспорт всех страниц не должен ломать
  // Ctrl+Z на открытой пользователем странице.
  const fresh = (await getPageDetails(page.id, false)) || page

  const dbBlocks = await getPageBlocks(page.id)
  const blocks: TextBlock[] = dbBlocks.map((b: any) => mapDbBlockToTextBlock(b))

  // Как и одиночный Export Page: если клина ещё нет, но есть текст, сначала
  // очищаем скан, иначе перевод запечётся поверх японского текста.
  let cleanPath = fresh.clean_path
  if (!cleanPath && blocks.length > 0) {
    const cleanRes = await runCleanPage(page.id, "auto")
    if (!cleanRes || cleanRes.success === false) {
      throw new Error(cleanRes?.error || "Ошибка клина")
    }
    cleanPath = cleanRes.clean_path
    ctx.onPageStatusUpdate?.(page.id, (cleanRes.page_status || "cleaned") as PageStatus, cleanRes.clean_path)
  }

  const baseImgUrl = cleanPath
    ? `${getPageCleanImageUrl(page.id)}?t=${Date.now()}`
    : getPageImageUrl(page.id)

  const baseImg = await loadImage(baseImgUrl)
  const blob = await bakePageBlob(baseImg, blocks, ctx.titleDefaultFontSize)

  if (!blob) {
    throw new Error("Не удалось сформировать PNG")
  }
  const res = await saveTranslatedPage(page.id, blob)
  if (!res || res.success === false) {
    throw new Error(res?.error || "Ошибка сохранения страницы")
  }
  ctx.onPageStatusUpdate?.(page.id, "done")
}

/** Экспорт JSON-скрипта главы в папку главы. */
export async function exportChapterScriptOp(ctx: BatchChapterOpsContext): Promise<void> {
  if (!ctx.chapterId) return
  await ctx.ensureCurrentPageSaved()

  ctx.setProgress({ action: "script-export", done: 0, total: 1, label: "Saving JSON to chapter folder..." })
  try {
    const res = await exportChapterScriptToFolder(ctx.chapterId)
    ctx.setJustFinished("script-export")
    setTimeout(() => ctx.setJustFinished(null), 2500)
    alert(`Скрипт главы успешно сохранён в папку:\n${res.saved_path}`)
  } catch (e) {
    alert("Ошибка сохранения скрипта: " + String(e))
  } finally {
    ctx.setProgress(null)
  }
}

/** Импорт скрипта: сначала пробуем нативный диалог бэкенда, иначе открываем выбор файла. */
export async function importChapterScriptOp(ctx: BatchChapterOpsContext, isRunning: boolean): Promise<void> {
  if (!ctx.chapterId || isRunning) return
  await ctx.ensureCurrentPageSaved()

  ctx.setProgress({ action: "script-import", done: 0, total: 1, label: "Checking chapter folder for dialogues JSON..." })
  try {
    const res = await pickAndImportChapterScript(ctx.chapterId)

    if (res.cancelled) {
      ctx.setProgress(null)
      return
    }

    if (res.success) {
      // Обновляем только страницы, куда действительно попал перевод.
      // Старый бэкенд без updated_page_ids — статусы не трогаем.
      if (Array.isArray(res.updated_page_ids)) {
        res.updated_page_ids.forEach((pageId) => {
          const page = ctx.pages.find((p) => p.id === pageId)
          if (page && page.status !== "done") {
            ctx.onPageStatusUpdate?.(pageId, "translated")
          }
        })
      }

      const msg = [
        res.auto_found ? "⚡ Файл найден автоматически в папке главы!" : null,
        `Файл: ${res.file_path}`,
        `Успешно импортировано реплик: ${res.updated_count}`,
        res.updated_speakers_count ? `Распознано спикеров: ${res.updated_speakers_count}` : null,
      ]
        .filter(Boolean)
        .join("\n")

      alert(msg)
      ctx.setJustFinished("script-import")
      setTimeout(() => ctx.setJustFinished(null), 2000)
      ctx.onCompleteBatch?.()
      ctx.onRefreshCurrent("script-import")
    } else {
      ctx.fileInputRef.current?.click()
    }
  } catch (err) {
    // Не глотаем ошибку: если файл в папке битый, пользователь должен увидеть
    // причину, а затем уже решить, выбирать ли другой файл вручную.
    console.error("Автоматический импорт скрипта не удался:", err)
    alert("Не удалось импортировать скрипт главы:\n" + String(err))
    ctx.fileInputRef.current?.click()
  } finally {
    ctx.setProgress(null)
  }
}

/** Импорт выбранного в браузере JSON-файла со скриптом. */
export async function importChapterScriptFileOp(
  ctx: BatchChapterOpsContext,
  e: React.ChangeEvent<HTMLInputElement>
): Promise<void> {
  const file = e.target.files?.[0]
  if (!file || !ctx.chapterId) return

  await ctx.ensureCurrentPageSaved()

  ctx.setProgress({ action: "script-import", done: 0, total: 1, label: "Importing translations & speakers..." })
  try {
    const res = await uploadChapterScript(ctx.chapterId, file)
    if (Array.isArray(res.updated_page_ids)) {
      res.updated_page_ids.forEach((pageId) => {
        const page = ctx.pages.find((p) => p.id === pageId)
        if (page && page.status !== "done") {
          ctx.onPageStatusUpdate?.(pageId, "translated")
        }
      })
    }

    const msg = [
      `Успешно импортировано реплик: ${res.updated_count}`,
      res.updated_speakers_count ? `Распознано спикеров: ${res.updated_speakers_count}` : null,
    ]
      .filter(Boolean)
      .join("\n")

    alert(msg)
    ctx.setJustFinished("script-import")
    setTimeout(() => ctx.setJustFinished(null), 2000)
  } catch (err) {
    alert("Ошибка импорта: " + String(err))
  } finally {
    ctx.setProgress(null)
    if (ctx.fileInputRef.current) ctx.fileInputRef.current.value = ""
    ctx.onCompleteBatch?.()
    ctx.onRefreshCurrent("script-import")
  }
}

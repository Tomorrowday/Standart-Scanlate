// manga_ui/hooks/use-batch-chapter-actions.ts
// Бизнес-логика пакетных операций над главой: Detect, Clean, Translate, Export и импорт/экспорт JSON

"use client"

import { useState, useRef } from "react"
import type { PageItem, TextBlock } from "@/lib/types"
import {
  runPageAutoDetect,
  runCleanPage,
  saveTranslatedPage,
  runTranslateChapter,
  getPageDetails,
  getPageCleanImageUrl,
  getPageImageUrl,
  getPageBlocks,
  exportChapterScriptToFolder,
  uploadChapterScript,
  pickAndImportChapterScript,
} from "@/lib/api"
import { loadImage, bakePageBlob, mapDbBlockToTextBlock } from "@/lib/typeset"
import type {
  BatchChapterActionsProps,
  BatchChapterActionsController,
  BatchAction,
  BatchProgress,
} from "@/components/batch-chapter-actions"

const ACTION_LABELS: Record<BatchAction, string> = {
  detect: "Detecting & OCR",
  clean: "Smart Cleaning & Retouching (AI)",
  translate: "Translating chapter with Gemini",
  export: "Exporting pages",
  "script-export": "Exporting JSON script to folder...",
  "script-import": "Importing JSON script...",
}

export type UseBatchChapterActionsReturn = BatchChapterActionsController

export function useBatchChapterActions({
  pages,
  titleDefaultFontSize = 14,
  onSaveCurrentPage,
  onPageStatusUpdate,
  onRefreshCurrent,
  onCompleteBatch,
}: BatchChapterActionsProps): UseBatchChapterActionsReturn {
  const [progress, setProgress] = useState<BatchProgress | null>(null)
  const [justFinished, setJustFinished] = useState<BatchAction | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const isRunning = progress !== null
  const percent = progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0
  const chapterId = pages[0]?.chapter_id

  const ensureCurrentPageSaved = async () => {
    if (onSaveCurrentPage) {
      try {
        await onSaveCurrentPage()
      } catch (err) {
        console.warn("Не удалось сохранить текущую страницу перед пакетным действием:", err)
      }
    }
  }

  const runBatch = async (action: BatchAction, worker: (page: PageItem, index: number) => Promise<void>) => {
    if (pages.length === 0 || isRunning) return

    await ensureCurrentPageSaved()

    setJustFinished(null)
    setProgress({ action, done: 0, total: pages.length, label: ACTION_LABELS[action] })

    const failedPages: string[] = []

    try {
      for (let i = 0; i < pages.length; i++) {
        const page = pages[i]
        setProgress({ action, done: i, total: pages.length, label: `${ACTION_LABELS[action]} · p.${page.page_number}` })
        try {
          await worker(page, i)
        } catch (e) {
          console.error(`Пакетная ошибка (${action}) на странице ${page.id}:`, e)
          failedPages.push(`стр. ${page.page_number} (${e instanceof Error ? e.message : String(e)})`)
        }
      }

      if (failedPages.length < pages.length) {
        setProgress({ action, done: pages.length, total: pages.length, label: "Done" })
        setJustFinished(action)
        setTimeout(() => setJustFinished(null), 2500)
      }

      if (failedPages.length > 0) {
        alert(
          `Операция "${ACTION_LABELS[action]}" завершена с ошибками (${failedPages.length} из ${pages.length}):\n` +
          failedPages.slice(0, 10).join("\n")
        )
      }
    } finally {
      setProgress(null)
      onCompleteBatch?.()
      onRefreshCurrent()
    }
  }

  const detectAll = () =>
    runBatch("detect", async (page) => {
      if (page.status !== "raw" && page.status !== "new") {
        return
      }
      const res = await runPageAutoDetect(page.id)
      if (!res || res.success === false) {
        throw new Error(res?.error || "Ошибка детекции")
      }
      onPageStatusUpdate?.(page.id, "detected")
    })

  const cleanChapter = () =>
    runBatch("clean", async (page) => {
      const res = await runCleanPage(page.id)
      if (!res || res.success === false) {
        throw new Error(res?.error || "Ошибка клина")
      }
      onPageStatusUpdate?.(page.id, res.page_status || "cleaned", res.clean_path)
    })

  const translateChapter = async () => {
    if (!chapterId || isRunning) return

    await ensureCurrentPageSaved()

    setJustFinished(null)
    setProgress({
      action: "translate",
      done: 0,
      total: 1,
      label: "Translating entire chapter via Gemini...",
    })

    try {
      await runTranslateChapter(chapterId)
      pages.forEach((p) => {
        if (p.status !== "done") {
          onPageStatusUpdate?.(p.id, "translated")
        }
      })
      setProgress({
        action: "translate",
        done: 1,
        total: 1,
        label: "Chapter translated!",
      })
      setJustFinished("translate")
      setTimeout(() => setJustFinished(null), 2500)
    } catch (e) {
      console.error("Ошибка перевода главы:", e)
      alert("Ошибка перевода главы: " + String(e))
    } finally {
      setProgress(null)
      onCompleteBatch?.()
      onRefreshCurrent()
    }
  }

  const exportAll = async () => {
    if (pages.length === 0 || isRunning) return

    await ensureCurrentPageSaved()

    await runBatch("export", async (page) => {
      const fresh = (await getPageDetails(page.id)) || page

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
        onPageStatusUpdate?.(page.id, cleanRes.page_status || "cleaned", cleanRes.clean_path)
      }

      const baseImgUrl = cleanPath
        ? `${getPageCleanImageUrl(page.id)}?t=${Date.now()}`
        : getPageImageUrl(page.id)

      const baseImg = await loadImage(baseImgUrl)
      const blob = await bakePageBlob(baseImg, blocks, titleDefaultFontSize)

      if (!blob) {
        throw new Error("Не удалось сформировать PNG")
      }
      const res = await saveTranslatedPage(page.id, blob)
      if (!res || res.success === false) {
        throw new Error(res?.error || "Ошибка сохранения страницы")
      }
      onPageStatusUpdate?.(page.id, "done")
    })
  }

  const handleExportScript = async () => {
    if (!chapterId) return
    await ensureCurrentPageSaved()

    setProgress({ action: "script-export", done: 0, total: 1, label: "Saving JSON to chapter folder..." })
    try {
      const res = await exportChapterScriptToFolder(chapterId)
      setJustFinished("script-export")
      setTimeout(() => setJustFinished(null), 2500)
      alert(`Скрипт главы успешно сохранён в папку:\n${res.saved_path}`)
    } catch (e) {
      alert("Ошибка сохранения скрипта: " + String(e))
    } finally {
      setProgress(null)
    }
  }

  const handleImportClick = async () => {
    if (!chapterId || isRunning) return
    await ensureCurrentPageSaved()

    setProgress({ action: "script-import", done: 0, total: 1, label: "Checking chapter folder for dialogues JSON..." })
    try {
      const res = await pickAndImportChapterScript(chapterId)

      if (res.cancelled) {
        setProgress(null)
        return
      }

      if (res.success) {
        pages.forEach((p) => {
          if (p.status !== "done") {
            onPageStatusUpdate?.(p.id, "translated")
          }
        })

        const msg = [
          res.auto_found ? "⚡ Файл найден автоматически в папке главы!" : null,
          `Файл: ${res.file_path}`,
          `Успешно импортировано реплик: ${res.updated_count}`,
          res.updated_speakers_count ? `Распознано спикеров: ${res.updated_speakers_count}` : null,
        ]
          .filter(Boolean)
          .join("\n")

        alert(msg)
        setJustFinished("script-import")
        setTimeout(() => setJustFinished(null), 2000)
        onCompleteBatch?.()
        onRefreshCurrent()
      } else {
        fileInputRef.current?.click()
      }
    } catch (err) {
      console.warn("Диалог бэкенда не сработал, открываем браузерный выбор файла:", err)
      fileInputRef.current?.click()
    } finally {
      setProgress(null)
    }
  }

  const handleImportScriptFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !chapterId) return

    await ensureCurrentPageSaved()

    setProgress({ action: "script-import", done: 0, total: 1, label: "Importing translations & speakers..." })
    try {
      const res = await uploadChapterScript(chapterId, file)
      pages.forEach((p) => {
        if (p.status !== "done") {
          onPageStatusUpdate?.(p.id, "translated")
        }
      })

      const msg = [
        `Успешно импортировано реплик: ${res.updated_count}`,
        res.updated_speakers_count ? `Распознано спикеров: ${res.updated_speakers_count}` : null,
      ]
        .filter(Boolean)
        .join("\n")

      alert(msg)
      setJustFinished("script-import")
      setTimeout(() => setJustFinished(null), 2000)
    } catch (err) {
      alert("Ошибка импорта: " + String(err))
    } finally {
      setProgress(null)
      if (fileInputRef.current) fileInputRef.current.value = ""
      onCompleteBatch?.()
      onRefreshCurrent()
    }
  }

  return {
    progress,
    justFinished,
    fileInputRef,
    isRunning,
    percent,
    detectAll,
    cleanChapter,
    translateChapter,
    exportAll,
    handleExportScript,
    handleImportClick,
    handleImportScriptFile,
  }
}

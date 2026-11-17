// manga_ui/hooks/use-batch-chapter-actions.ts
// Бизнес-логика пакетных операций над главой: Detect, Clean, Translate, Export и импорт/экспорт JSON

"use client"

import { useState, useRef } from "react"
import type { PageItem } from "@/lib/types"
import {
  runPageAutoDetect,
  runCleanPage,
  runTranslateChapter,
} from "@/lib/api"
import {
  exportBakePageOp,
  exportChapterScriptOp,
  importChapterScriptFileOp,
  importChapterScriptOp,
  type BatchChapterOpsContext,
} from "./pipelines/batch-chapter-ops"
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

  const buildOpsCtx = (): BatchChapterOpsContext => ({
    pages,
    chapterId,
    titleDefaultFontSize,
    ensureCurrentPageSaved,
    setProgress,
    setJustFinished,
    fileInputRef,
    onPageStatusUpdate,
    onCompleteBatch,
    onRefreshCurrent,
  })

  const exportAll = () =>
    runBatch("export", (page) => exportBakePageOp(buildOpsCtx(), page))

  const handleExportScript = () => exportChapterScriptOp(buildOpsCtx())

  const handleImportClick = () => importChapterScriptOp(buildOpsCtx(), isRunning)

  const handleImportScriptFile = (e: React.ChangeEvent<HTMLInputElement>) =>
    importChapterScriptFileOp(buildOpsCtx(), e)

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

"use client"

// manga_ui/components/batch-chapter-actions.tsx
/**
 * Контракт панели пакетных операций над всеми страницами главы.
 */

import type { ChangeEvent, RefObject } from "react"
import type { PageItem, PageStatus } from "@/lib/types"
import { Wand2, Languages, Sparkles, Download, Loader2, Layers3, Check, FileDown, FileUp } from "lucide-react"
import { useBatchChapterActions } from "@/hooks/use-batch-chapter-actions"

export type BatchAction = "detect" | "clean" | "translate" | "export" | "script-export" | "script-import"

export interface BatchProgress {
  action: BatchAction
  done: number
  total: number
  label: string
}

/**
 * Внешний контроллер пакетных действий главы.
 * Позволяет поднять `useBatchChapterActions` в родителя (MangaTranslator)
 * и использовать одни и те же методы и в панели, и в глобальных хоткеях.
 */
export interface BatchChapterActionsController {
  progress: BatchProgress | null
  justFinished: BatchAction | null
  fileInputRef: RefObject<HTMLInputElement | null>
  isRunning: boolean
  percent: number
  detectAll: () => void
  cleanChapter: () => void
  translateChapter: () => Promise<void>
  exportAll: () => Promise<void>
  handleExportScript: () => Promise<void>
  handleImportClick: () => Promise<void>
  handleImportScriptFile: (e: ChangeEvent<HTMLInputElement>) => Promise<void>
}

export interface BatchChapterActionsProps {
  pages: PageItem[]
  currentPageId: number | null
  titleDefaultFontSize?: number
  onSaveCurrentPage?: () => Promise<void>
  onPageStatusUpdate?: (pageId: number, status: PageStatus, cleanPath?: string) => void
  onRefreshCurrent: (action?: BatchAction) => void
  onCompleteBatch?: () => void
  /** Если передан, панель использует его вместо собственного вызова `useBatchChapterActions` */
  controller?: BatchChapterActionsController
}

interface BatchChapterActionsViewProps {
  pages: BatchChapterActionsProps["pages"]
  controller: BatchChapterActionsController
}

function BatchChapterActionsView({ pages, controller }: BatchChapterActionsViewProps) {
  const {
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
  } = controller

  const buttons: Array<{ key: BatchAction; label: string; icon: typeof Wand2; onClick: () => void; accent: string }> = [
    { key: "detect", label: "Detect & OCR All", icon: Wand2, onClick: detectAll, accent: "text-indigo-400" },
    { key: "clean", label: "Smart Clean Chapter", icon: Sparkles, onClick: cleanChapter, accent: "text-purple-400" },
    { key: "translate", label: "Translate Chapter", icon: Languages, onClick: translateChapter, accent: "text-emerald-400" },
    { key: "export", label: "Export All", icon: Download, onClick: exportAll, accent: "text-amber-400" },
  ]

  const disabled = pages.length === 0

  return (
    <div className="flex items-center gap-3 border-b border-slate-800 bg-slate-950/40 px-6 py-2">
      <div className="flex shrink-0 items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
        <Layers3 className="h-4 w-4 text-indigo-400" />
        <span className="hidden sm:inline">Batch Chapter</span>
        <span className="ml-1 rounded-full bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
          {pages.length}p
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {buttons.map(({ key, label, icon: Icon, onClick, accent }) => {
          const active = progress?.action === key
          const done = justFinished === key
          return (
            <button
              key={key}
              onClick={onClick}
              disabled={disabled || isRunning}
              title={disabled ? "Open a chapter from the explorer first" : label}
              className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {active ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : done ? (
                <Check className="h-3.5 w-3.5 text-emerald-400" />
              ) : (
                <Icon className={`h-3.5 w-3.5 ${accent}`} />
              )}
              {label}
            </button>
          )
        })}

        <div className="mx-1 h-4 w-[1px] bg-slate-800 hidden sm:block" />

        <button
          onClick={handleExportScript}
          disabled={disabled || isRunning}
          className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white disabled:opacity-50"
          title="Сохранить JSON скрипт главы в локальную папку главы на диске"
        >
          {justFinished === "script-export" ? (
            <Check className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <FileDown className="h-3.5 w-3.5 text-sky-400" />
          )}
          Export JSON
        </button>

        <button
          onClick={handleImportClick}
          disabled={disabled || isRunning}
          className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white disabled:opacity-50"
          title="Автоматически импортировать файл диалогов из папки главы или выбрать файл"
        >
          {progress?.action === "script-import" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : justFinished === "script-import" ? (
            <Check className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <FileUp className="h-3.5 w-3.5 text-amber-400" />
          )}
          Import JSON
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.txt"
          onChange={handleImportScriptFile}
          className="hidden"
        />
      </div>

      <div className="ml-auto flex min-w-0 flex-1 items-center gap-3 sm:max-w-xs">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
          <div
            className={[
              "h-full rounded-full transition-all duration-300",
              isRunning ? "bg-indigo-500" : justFinished ? "bg-emerald-500" : "bg-transparent",
            ].join(" ")}
            style={{ width: isRunning ? `${percent}%` : justFinished ? "100%" : "0%" }}
          />
        </div>
        <span className="shrink-0 text-[11px] tabular-nums text-slate-500">
          {isRunning ? progress?.label : justFinished ? "Done" : "Idle"}
        </span>
      </div>
    </div>
  )
}

function BatchChapterActionsWithHook(props: BatchChapterActionsProps) {
  const controller = useBatchChapterActions(props)
  return <BatchChapterActionsView pages={props.pages} controller={controller} />
}

export function BatchChapterActions(props: BatchChapterActionsProps) {
  if (props.controller) {
    return <BatchChapterActionsView pages={props.pages} controller={props.controller} />
  }
  return <BatchChapterActionsWithHook {...props} />
}

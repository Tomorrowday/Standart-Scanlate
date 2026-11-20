"use client"

// manga_ui/components/translator-header.tsx
/**
 * Контракт шапки редактора (навигация по страницам, кегль тайтла, таймер главы, вызов статистики, сохранение/экспорт).
 */

import type { PageItem } from "@/lib/types"
import {
  BookText,
  FolderOpen,
  Loader2,
  Check,
  Download,
  Save,
  ChevronLeft,
  ChevronRight,
  Keyboard,
  Sliders,
  Type,
  CheckCheck,
  BarChart3,
  ZapOff,
} from "lucide-react"
import { useHotkeysConfig } from "@/hooks/use-manga-hotkeys"
import { ChapterTimerWidget } from "@/components/chapter-timer-widget"

export interface TranslatorHeaderProps {
  currentPage: PageItem | null
  currentIndex?: number
  totalPages?: number
  currentChapterId?: number | null
  titleFontSize: number
  onTitleFontSizeChange: (newSize: number) => void
  onApplyFontSizeToChapter: () => void
  isApplyingChapterFont: boolean
  isSaving: boolean
  isExporting: boolean
  isExportSuccess: boolean
  isUnloadingModels?: boolean
  unloadMessage?: string | null
  onUnloadModels?: () => void
  onOpenFolder: () => void
  onExportPage: () => void
  onSaveBlocks: () => void
  onPrevPage?: () => void
  onNextPage?: () => void
  onOpenHotkeys?: () => void
  onOpenSettings?: () => void
  onOpenStatistics?: () => void
}

export function TranslatorHeader({
  currentPage,
  currentIndex = -1,
  totalPages = 0,
  currentChapterId,
  titleFontSize,
  onTitleFontSizeChange,
  onApplyFontSizeToChapter,
  isApplyingChapterFont,
  isSaving,
  isExporting,
  isExportSuccess,
  isUnloadingModels = false,
  unloadMessage = null,
  onUnloadModels,
  onOpenFolder,
  onExportPage,
  onSaveBlocks,
  onPrevPage,
  onNextPage,
  onOpenHotkeys,
  onOpenSettings,
  onOpenStatistics,
}: TranslatorHeaderProps) {
  const { hotkeys } = useHotkeysConfig()
  const hasPrev = currentIndex > 0
  const hasNext = currentIndex >= 0 && currentIndex < totalPages - 1

  return (
    <header className="flex items-center justify-between border-b border-slate-800 bg-slate-950/60 px-6 py-2.5 select-none">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500 shadow-md">
          <BookText className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-sm font-semibold leading-tight text-white">Manga Translator</h1>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {currentPage ? (
              <>
                <span className="font-semibold text-slate-200">
                  Page {currentPage.page_number}
                  {totalPages > 0 && <span className="text-slate-500 font-normal"> / {totalPages}</span>}
                </span>

                <div className="flex items-center rounded border border-slate-800 bg-slate-900 p-0.5">
                  <button
                    onClick={onPrevPage}
                    disabled={!hasPrev}
                    className="flex h-5 w-5 items-center justify-center rounded text-slate-300 hover:bg-slate-800 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent"
                    title={`Предыдущая страница (${hotkeys.prevPage.label})`}
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={onNextPage}
                    disabled={!hasNext}
                    className="flex h-5 w-5 items-center justify-center rounded text-slate-300 hover:bg-slate-800 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent"
                    title={`Следующая страница (${hotkeys.nextPage.label})`}
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>

                <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                  DB ID: {currentPage.id}
                </span>
              </>
            ) : (
              "No page selected"
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2.5 text-xs text-slate-400">
        {/* Трекинг времени текущей главы: тик изолирован внутри виджета */}
        <ChapterTimerWidget chapterId={currentChapterId ?? null} />

        {/* Кнопка полной выгрузки нейросетей из VRAM и RAM */}
        <button
          type="button"
          onClick={onUnloadModels}
          disabled={isUnloadingModels}
          className={[
            "flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors",
            unloadMessage
              ? "border-emerald-500/60 bg-emerald-600/20 text-emerald-300"
              : "border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-white",
            isUnloadingModels ? "opacity-60" : "",
          ].join(" ")}
          title="Полностью выгрузить YOLO, OCR, LaMa и NLP-модели словаря из VRAM и RAM"
        >
          {isUnloadingModels ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />
          ) : unloadMessage ? (
            <Check className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <ZapOff className="h-3.5 w-3.5 text-amber-400" />
          )}
          {unloadMessage ?? "Очистить VRAM"}
        </button>

        {/* Кнопка открытия расширенной статистики тайтлов и глав */}
        <button
          onClick={onOpenStatistics}
          className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-indigo-300 hover:bg-slate-800 hover:text-white transition-colors"
          title="Открыть окно статистики реплик, слов и времени по главам"
        >
          <BarChart3 className="h-3.5 w-3.5 text-indigo-400" />
          Статистика
        </button>

        {/* Контроллер базового размера шрифта тайтла + Кнопка применения к главе */}
        <div className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 p-1 text-xs">
          <div className="flex items-center gap-1 px-1">
            <Type className="h-3.5 w-3.5 text-indigo-400" />
            <span className="text-[11px] font-medium text-slate-300">Кегль:</span>
            <button
              type="button"
              onClick={() => onTitleFontSizeChange(Math.max(8, titleFontSize - 1))}
              className="h-5 w-5 rounded bg-slate-800 font-mono font-bold text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
            >
              -
            </button>
            <span className="min-w-[30px] text-center font-mono font-bold text-indigo-300">
              {titleFontSize}px
            </span>
            <button
              type="button"
              onClick={() => onTitleFontSizeChange(Math.min(48, titleFontSize + 1))}
              className="h-5 w-5 rounded bg-slate-800 font-mono font-bold text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
            >
              +
            </button>
          </div>

          <button
            type="button"
            disabled={!currentPage || isApplyingChapterFont}
            onClick={onApplyFontSizeToChapter}
            className="flex items-center gap-1 rounded bg-indigo-600/40 hover:bg-indigo-600 px-2 py-0.5 text-[11px] font-medium text-indigo-200 hover:text-white transition-all disabled:opacity-40"
            title="Сбросить все баблы текущей главы в режим Auto по этому базовому кеглю"
          >
            {isApplyingChapterFont ? (
              <Loader2 className="h-3 w-3 animate-spin text-white" />
            ) : (
              <CheckCheck className="h-3 w-3 text-indigo-300" />
            )}
            Применить к главе
          </button>
        </div>

        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
          title="Глобальные настройки (модели, тогглы)"
        >
          <Sliders className="h-3.5 w-3.5 text-amber-400" />
          Настройки
        </button>

        <button
          onClick={onOpenHotkeys}
          className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
          title="Настройка горячих клавиш"
        >
          <Keyboard className="h-3.5 w-3.5 text-indigo-400" />
          Хоткеи
        </button>

        {currentPage && (
          <>
            <button
              onClick={onOpenFolder}
              className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
              title="Открыть готовую папку в Explorer"
            >
              <FolderOpen className="h-3.5 w-3.5 text-amber-400" />
              Folder
            </button>

            <button
              onClick={onExportPage}
              disabled={isExporting}
              className={[
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-white transition-all shadow-sm",
                isExportSuccess
                  ? "bg-emerald-500 ring-2 ring-emerald-300"
                  : "bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50",
              ].join(" ")}
              title="Запечь страницу на сервере в папку translated"
            >
              {isExporting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : isExportSuccess ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {isExportSuccess ? "Saved to folder!" : "Export Page"}
            </button>

            <button
              onClick={onSaveBlocks}
              disabled={isSaving}
              className="flex items-center gap-1.5 rounded-md bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700 disabled:opacity-50"
              title={`Save (${hotkeys.savePage.label})`}
            >
              {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              Save
            </button>
          </>
        )}
      </div>
    </header>
  )
}

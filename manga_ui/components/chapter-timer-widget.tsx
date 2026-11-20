"use client"

// manga_ui/components/chapter-timer-widget.tsx
/**
 * Изолированный виджет таймера главы.
 *
 * Секундный тик живёт здесь, а не в корневом MangaTranslator: иначе раз в
 * секунду перерисовывалось всё дерево (карточки баблов, пайплайны, хоткеи).
 */

import { Clock, Play, Square } from "lucide-react"
import { useChapterTimer } from "@/hooks/use-chapter-timer"

export interface ChapterTimerWidgetProps {
  chapterId: number | null
}

function formatTimer(totalSec: number): string {
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
  }
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
}

export function ChapterTimerWidget({ chapterId }: ChapterTimerWidgetProps) {
  const { isTimerRunning, timerSeconds, handleStartTimer, handleStopTimer } =
    useChapterTimer(chapterId)

  return (
    <div className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2 py-1">
      <Clock className={`h-3.5 w-3.5 ${isTimerRunning ? "text-emerald-400 animate-pulse" : "text-slate-400"}`} />
      <span className={`font-mono text-xs font-semibold ${isTimerRunning ? "text-emerald-300" : "text-slate-300"}`}>
        {formatTimer(timerSeconds)}
      </span>

      <button
        type="button"
        disabled={!chapterId || isTimerRunning}
        onClick={handleStartTimer}
        className="flex items-center gap-1 rounded bg-emerald-600/30 hover:bg-emerald-600 px-2 py-0.5 text-[11px] font-medium text-emerald-200 hover:text-white transition-all disabled:opacity-30"
        title="Запустить таймер работы над текущей главой"
      >
        <Play className="h-3 w-3 fill-current" />
        Старт
      </button>

      <button
        type="button"
        disabled={!chapterId || !isTimerRunning}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={handleStopTimer}
        className="flex items-center gap-1 rounded bg-rose-600/30 hover:bg-rose-600 px-2 py-0.5 text-[11px] font-medium text-rose-200 hover:text-white transition-all disabled:opacity-30"
        title="Остановить таймер и зафиксировать время в БД"
      >
        <Square className="h-3 w-3 fill-current" />
        Стоп
      </button>
    </div>
  )
}

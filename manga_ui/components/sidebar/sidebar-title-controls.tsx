// manga_ui/components/sidebar/sidebar-title-controls.tsx
// Выбор тайтла и кнопки управления: «О тайтле», «Скан», «+ Глава», удаление тайтла

import { Trash2, BookOpen, RefreshCw, Loader2, FolderPlus } from "lucide-react"
import type { TitleProject } from "@/lib/types"

export interface SidebarTitleControlsProps {
  projectList: TitleProject[]
  selectedTitleId: number | null
  isRescanning: boolean
  onSelectTitle: (titleId: number) => void
  onDeleteTitle: (titleId: number) => void
  onOpenGlossary: () => void
  onRescan: () => void
  onAddChapterClick: () => void
}

export function SidebarTitleControls({
  projectList,
  selectedTitleId,
  isRescanning,
  onSelectTitle,
  onDeleteTitle,
  onOpenGlossary,
  onRescan,
  onAddChapterClick,
}: SidebarTitleControlsProps) {
  return (
    <div className="border-b border-slate-800 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <select
          value={selectedTitleId || ""}
          onChange={(e) => onSelectTitle(Number(e.target.value))}
          className="w-full rounded border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500"
        >
          {projectList.length === 0 ? (
            <option value="">No titles scanned</option>
          ) : (
            projectList.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))
          )}
        </select>

        {selectedTitleId && (
          <button
            onClick={() => onDeleteTitle(selectedTitleId)}
            className="rounded p-1.5 text-slate-500 hover:bg-slate-800 hover:text-rose-400 transition-colors"
            title="Удалить тайтл из базы"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {selectedTitleId && (
        <div className="grid grid-cols-3 gap-1 pt-0.5">
          <button
            onClick={onOpenGlossary}
            className="flex items-center justify-center gap-1 rounded border border-slate-800 bg-slate-900 py-1 text-[11px] font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
            title="Глоссарий, персонажи и синопсис тайтла"
          >
            <BookOpen className="h-3.5 w-3.5 text-indigo-400" />
            О тайтле
          </button>

          <button
            onClick={onRescan}
            disabled={isRescanning}
            className="flex items-center justify-center gap-1 rounded border border-slate-800 bg-slate-900 py-1 text-[11px] font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors disabled:opacity-50"
            title="Проверить папку на новые главы (существующие не трогать)"
          >
            {isRescanning ? (
              <Loader2 className="h-3 w-3 animate-spin text-sky-400" />
            ) : (
              <RefreshCw className="h-3 w-3 text-sky-400" />
            )}
            Скан
          </button>

          <button
            onClick={onAddChapterClick}
            className="flex items-center justify-center gap-1 rounded border border-slate-800 bg-indigo-950/40 py-1 text-[11px] font-medium text-indigo-300 hover:bg-indigo-900/60 hover:text-indigo-100 transition-colors"
            title="Добавить главу в этот тайтл"
          >
            <FolderPlus className="h-3 w-3 text-indigo-400" />
            + Глава
          </button>
        </div>
      )}
    </div>
  )
}

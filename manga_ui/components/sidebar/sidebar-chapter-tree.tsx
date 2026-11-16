// manga_ui/components/sidebar/sidebar-chapter-tree.tsx
// Аккордеон глав и список страниц с индикаторами статуса готовности

import {
  ChevronDown,
  ChevronRight,
  Trash2,
  FileImage,
  Folder,
  Loader2,
} from "lucide-react"
import type { ProjectTree, PageItem, PageStatus, ChapterItem } from "@/lib/types"

const STATUS_CONFIG: Record<PageStatus, { color: string; label: string }> = {
  raw: { color: "bg-slate-600", label: "Raw (Без разметки)" },
  new: { color: "bg-slate-600", label: "Raw (Новая)" },
  detected: { color: "bg-sky-400", label: "Detected (OCR готов)" },
  cleaned: { color: "bg-purple-400", label: "Cleaned (Скан очищен)" },
  translated: { color: "bg-amber-400", label: "Translated (Переведено)" },
  done: { color: "bg-emerald-400", label: "Done (Экспортировано)" },
}

export interface SidebarChapterTreeProps {
  projectTree: ProjectTree | null
  loadingTree: boolean
  expandedChapters: Record<number, boolean>
  currentPageId: number | null
  onToggleChapter: (chapterId: number) => void
  onDeleteChapter: (e: React.MouseEvent, chapterId: number, chapterNum: string) => void
  onSelectPage: (page: PageItem, chapterPages: PageItem[]) => void
}

export function SidebarChapterTree({
  projectTree,
  loadingTree,
  expandedChapters,
  currentPageId,
  onToggleChapter,
  onDeleteChapter,
  onSelectPage,
}: SidebarChapterTreeProps) {
  return (
    <div className="flex-1 overflow-y-auto p-2">
      {loadingTree ? (
        <div className="flex h-32 items-center justify-center gap-2 text-xs text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : !projectTree || !projectTree.chapters || projectTree.chapters.length === 0 ? (
        <div className="p-4 text-center text-xs text-slate-600">
          В этом тайтле пока нет глав. Нажмите «+ Глава» или «Скан», чтобы добавить.
        </div>
      ) : (
        <div className="space-y-1">
          {projectTree.chapters.map((ch: ChapterItem) => {
            const isExpanded = !!expandedChapters[ch.id]
            return (
              <div key={ch.id} className="group/ch rounded-md">
                <div className="flex items-center justify-between rounded px-2 py-1.5 hover:bg-slate-900">
                  <button
                    onClick={() => onToggleChapter(ch.id)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs font-medium text-slate-300"
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                    )}
                    <Folder className="h-3.5 w-3.5 shrink-0 text-amber-500/80" />
                    <span className="truncate">{ch.chapter_number}</span>
                    <span className="ml-1 text-[10px] text-slate-600">({ch.pages.length}p)</span>
                  </button>

                  <button
                    onClick={(e) => onDeleteChapter(e, ch.id, ch.chapter_number)}
                    className="rounded p-1 text-slate-600 opacity-0 group-hover/ch:opacity-100 hover:bg-slate-800 hover:text-rose-400 transition-all"
                    title="Удалить только эту главу"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>

                {isExpanded && (
                  <div className="ml-4 mt-0.5 space-y-0.5 border-l border-slate-800 pl-2">
                    {ch.pages.map((p: PageItem) => {
                      const isSelected = p.id === currentPageId
                      const statusConfig = STATUS_CONFIG[p.status as PageStatus] || STATUS_CONFIG.raw

                      return (
                        <button
                          key={p.id}
                          onClick={() => {
                            onSelectPage(p, ch.pages)
                          }}
                          className={[
                            "flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs transition-colors",
                            isSelected
                              ? "bg-indigo-600/30 font-medium text-indigo-200"
                              : "text-slate-400 hover:bg-slate-900 hover:text-slate-200",
                          ].join(" ")}
                        >
                          <FileImage className="h-3 w-3 shrink-0" />
                          <span className="truncate">Page {p.page_number}</span>
                          <span
                            className={`ml-auto h-2 w-2 rounded-full ${statusConfig.color}`}
                            title={`Status: ${statusConfig.label}`}
                          />
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

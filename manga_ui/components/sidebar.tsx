"use client"

// manga_ui/components/sidebar.tsx
/**
 * Контракт боковой панели (Explorer проектов, глав и страниц с управлением).
 */

import type { PageStatus } from "@/lib/types"
import { useState, useEffect, useCallback } from "react"
import { FolderTree, Plus, PanelLeftClose, PanelLeftOpen } from "lucide-react"
import type { TitleProject, ProjectTree, PageItem, ChapterItem } from "@/lib/types"
import {
  getProjects,
  getProjectTree,
  scanProjectFolder,
  rescanProject,
  addChapterToProject,
  deleteChapter,
  deleteProject,
} from "@/lib/api"
import { ProjectModal } from "@/components/project-modal"
import { SidebarModals } from "@/components/sidebar/sidebar-modals"
import { SidebarTitleControls } from "@/components/sidebar/sidebar-title-controls"
import { SidebarChapterTree } from "@/components/sidebar/sidebar-chapter-tree"

export interface SidebarProps {
  currentPageId: number | null
  activePageUpdate?: { id: number; status: PageStatus; clean_path?: string } | null
  refreshTrigger?: number
  onSelectPage: (page: PageItem, chapterPages?: PageItem[]) => void
  onChapterDeleted?: (chapterId: number) => void
  onTitleSelected?: (titleId: number, defaultFontSize?: number) => void
}

export function Sidebar({
  currentPageId,
  activePageUpdate,
  refreshTrigger,
  onSelectPage,
  onChapterDeleted,
  onTitleSelected,
}: SidebarProps) {
  const [isOpen, setIsOpen] = useState(true)
  const [projects, setProjects] = useState<TitleProject[]>([])
  const [selectedTitleId, setSelectedTitleId] = useState<number | null>(null)
  const [projectTree, setProjectTree] = useState<ProjectTree | null>(null)
  const [expandedChapters, setExpandedChapters] = useState<Record<number, boolean>>({})

  const [loadingTree, setLoadingTree] = useState(false)
  const [isRescanning, setIsRescanning] = useState(false)

  const [showScanModal, setShowScanModal] = useState(false)
  const [showAddChapterModal, setShowAddChapterModal] = useState(false)

  const [showProjectModal, setShowProjectModal] = useState(false)
  const [projectModalTab, setProjectModalTab] = useState<"glossary" | "synopsis">("glossary")

  const loadProjects = useCallback(async () => {
    try {
      const response: any = await getProjects()
      const list: TitleProject[] = Array.isArray(response)
        ? response
        : Array.isArray(response?.projects)
        ? response.projects
        : []

      setProjects(list)
      setSelectedTitleId((prev) => {
        if (prev !== null && list.some((p: TitleProject) => p.id === prev)) {
          return prev
        }
        return list.length > 0 ? list[0].id : null
      })
    } catch (e) {
      console.error("Ошибка загрузки проектов:", e)
      setProjects([])
    }
  }, [])

  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  const loadTree = useCallback(async (titleId: number) => {
    setLoadingTree(true)
    try {
      const tree = await getProjectTree(titleId)
      setProjectTree(tree)
      onTitleSelected?.(titleId, tree.default_font_size)
      if (tree.chapters && tree.chapters.length > 0) {
        setExpandedChapters((prev) => (Object.keys(prev).length === 0 ? { [tree.chapters[0].id]: true } : prev))
      }
    } catch (e) {
      console.error("Ошибка загрузки глав:", e)
    } finally {
      setLoadingTree(false)
    }
  }, [onTitleSelected])

  useEffect(() => {
    if (selectedTitleId) {
      loadTree(selectedTitleId)
    } else {
      setProjectTree(null)
    }
  }, [selectedTitleId, loadTree, refreshTrigger])

  useEffect(() => {
    if (!activePageUpdate) return

    setProjectTree((prev: ProjectTree | null) => {
      if (!prev || !prev.chapters) return prev
      const updatedChapters = prev.chapters.map((ch: ChapterItem) => ({
        ...ch,
        pages: ch.pages.map((p: PageItem) =>
          p.id === activePageUpdate.id
            ? {
                ...p,
                status: activePageUpdate.status,
                clean_path: activePageUpdate.clean_path !== undefined ? activePageUpdate.clean_path : p.clean_path,
              }
            : p
        ),
      }))
      return { ...prev, chapters: updatedChapters }
    })
  }, [activePageUpdate])

  const toggleChapter = (chapterId: number) => {
    setExpandedChapters((prev) => ({ ...prev, [chapterId]: !prev[chapterId] }))
  }

  const handleScanProject = async (name: string, path: string): Promise<boolean> => {
    try {
      const res = await scanProjectFolder(name, path)
      if (res.success) {
        await loadProjects()
        return true
      }
      alert("Ошибка: " + (res.error || "Неизвестная ошибка"))
      return false
    } catch (e) {
      alert("Не удалось отсканировать папку: " + String(e))
      return false
    }
  }

  const handleAddChapter = async (path: string, chNum?: string): Promise<boolean> => {
    if (!selectedTitleId) return false
    try {
      const res = await addChapterToProject(selectedTitleId, path, chNum)
      if (res.success) {
        await loadTree(selectedTitleId)
        return true
      }
      alert("Ошибка: " + (res.error || res.detail || "Неизвестная ошибка"))
      return false
    } catch (e) {
      alert("Не удалось добавить главу: " + String(e))
      return false
    }
  }

  const handleRescanTitle = async () => {
    if (!selectedTitleId || isRescanning) return
    setIsRescanning(true)
    try {
      const res = await rescanProject(selectedTitleId)
      alert(res.message || "Сканирование завершено!")
      await loadTree(selectedTitleId)
    } catch (err) {
      alert("Ошибка повторного сканирования: " + String(err))
    } finally {
      setIsRescanning(false)
    }
  }

  const handleDeleteChapter = async (e: React.MouseEvent, chapterId: number, chapterNum: string) => {
    e.stopPropagation()
    if (!confirm(`Удалить главу "${chapterNum}" из этого тайтла? Сканы на диске останутся нетронутыми.`)) return

    try {
      const res = await deleteChapter(chapterId)
      if (res.success) {
        onChapterDeleted?.(chapterId)
        if (selectedTitleId) {
          await loadTree(selectedTitleId)
        }
      }
    } catch (err) {
      alert("Ошибка удаления главы: " + String(err))
    }
  }

  const handleDeleteTitle = async (titleId: number) => {
    if (!confirm("Удалить этот тайтл из базы? Файлы на диске затронуты не будут.")) return
    await deleteProject(titleId)
    setSelectedTitleId(null)
    await loadProjects()
  }

  const projectList = Array.isArray(projects) ? projects : []
  const selectedProject = projectList.find((p) => p.id === selectedTitleId)

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="absolute left-3 top-14 z-30 flex h-8 w-8 items-center justify-center rounded-md border border-slate-700 bg-slate-900/90 text-slate-400 backdrop-blur hover:bg-slate-800 hover:text-white"
        title="Open Project Explorer"
      >
        <PanelLeftOpen className="h-4 w-4" />
      </button>
    )
  }

  return (
    <aside className="relative flex h-full w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950/80">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <FolderTree className="h-4 w-4 text-indigo-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">Explorer</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowScanModal(true)}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-indigo-300 transition-colors"
            title="Сканировать новый тайтл"
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            title="Свернуть Explorer"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>
      </div>

      <SidebarTitleControls
        projectList={projectList}
        selectedTitleId={selectedTitleId}
        isRescanning={isRescanning}
        onSelectTitle={setSelectedTitleId}
        onDeleteTitle={handleDeleteTitle}
        onOpenGlossary={() => {
          setProjectModalTab("glossary")
          setShowProjectModal(true)
        }}
        onRescan={handleRescanTitle}
        onAddChapterClick={() => setShowAddChapterModal(true)}
      />

      <SidebarChapterTree
        projectTree={projectTree}
        loadingTree={loadingTree}
        expandedChapters={expandedChapters}
        currentPageId={currentPageId}
        onToggleChapter={toggleChapter}
        onDeleteChapter={handleDeleteChapter}
        onSelectPage={onSelectPage}
      />

      <SidebarModals
        showScanModal={showScanModal}
        showAddChapterModal={showAddChapterModal}
        selectedProjectName={selectedProject?.name}
        onCloseScanModal={() => setShowScanModal(false)}
        onCloseAddChapterModal={() => setShowAddChapterModal(false)}
        onScanProject={handleScanProject}
        onAddChapter={handleAddChapter}
      />

      {showProjectModal && selectedTitleId && (
        <ProjectModal
          titleId={selectedTitleId}
          titleName={selectedProject?.name || "Проект"}
          initialTab={projectModalTab}
          onClose={() => setShowProjectModal(false)}
        />
      )}
    </aside>
  )
}

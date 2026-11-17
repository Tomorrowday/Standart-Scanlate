// manga_ui/hooks/use-manga-page-state.ts
// Состояние активной страницы (обновления статуса) и список известных спикеров

import { useState, useCallback } from "react"
import type { PageItem, PageStatus } from "@/lib/types"
import { getPageSpeakers } from "@/lib/api"

export interface PageStatusUpdate {
  id: number
  status: PageStatus
  clean_path?: string
}

export interface UseMangaPageStateProps {
  setCurrentPage: React.Dispatch<React.SetStateAction<PageItem | null>>
  setChapterPages: React.Dispatch<React.SetStateAction<PageItem[]>>
  setViewMode: (mode: "original" | "clean") => void
  setCleanCacheBuster: (value: number) => void
}

export interface UseMangaPageStateReturn {
  activePageUpdate: PageStatusUpdate | null
  handlePageStatusUpdate: (pageId: number, status: PageStatus, cleanPath?: string) => void
  knownSpeakers: string[]
  refreshSpeakersList: (pageId: number) => Promise<void>
}

export function useMangaPageState({
  setCurrentPage,
  setChapterPages,
  setViewMode,
  setCleanCacheBuster,
}: UseMangaPageStateProps): UseMangaPageStateReturn {
  const [knownSpeakers, setKnownSpeakers] = useState<string[]>([])
  const [activePageUpdate, setActivePageUpdate] = useState<PageStatusUpdate | null>(null)

  const refreshSpeakersList = useCallback(async (pageId: number) => {
    try {
      const speakers = await getPageSpeakers(pageId)
      if (speakers?.length) setKnownSpeakers(speakers)
    } catch (e) {
      console.error("Ошибка спикеров:", e)
    }
  }, [])

  const handlePageStatusUpdate = useCallback((pageId: number, status: PageStatus, cleanPath?: string) => {
    setActivePageUpdate({ id: pageId, status, clean_path: cleanPath })
    setCurrentPage((prev) => {
      if (!prev || prev.id !== pageId) return prev
      return {
        ...prev,
        status,
        clean_path: cleanPath !== undefined ? (cleanPath || undefined) : prev.clean_path,
      }
    })
    // Синхронизируем список страниц главы: иначе пакетные действия (например,
    // Detect & OCR All) увидят у обработанной страницы устаревший статус "raw".
    setChapterPages((prev) =>
      prev.map((p) =>
        p.id === pageId
          ? {
              ...p,
              status,
              clean_path: cleanPath !== undefined ? (cleanPath || undefined) : p.clean_path,
            }
          : p
      )
    )
    if (cleanPath !== undefined) {
      setCleanCacheBuster(Date.now())
      setViewMode(cleanPath ? "clean" : "original")
    }
  }, [setCurrentPage, setChapterPages, setViewMode, setCleanCacheBuster])

  return { activePageUpdate, handlePageStatusUpdate, knownSpeakers, refreshSpeakersList }
}

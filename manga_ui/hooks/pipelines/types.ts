// manga_ui/hooks/pipelines/types.ts
// Общий контекст пайплайнов обработки страницы

import type { PageItem, PageStatus, TextBlock, TitleSettings } from "@/lib/types"

export interface PagePipelineContext {
  currentPage: PageItem | null
  setCurrentPage: React.Dispatch<React.SetStateAction<PageItem | null>>
  textBlocks: TextBlock[]
  setTextBlocks: React.Dispatch<React.SetStateAction<TextBlock[]>>
  textBlocksRef: React.MutableRefObject<TextBlock[]>
  globalSettings: TitleSettings
  setSelectedId: (id: string | null) => void
  saveBlocks: (refreshSpeakers?: boolean) => Promise<void>
  /** Сохранение блоков конкретной страницы (безопасно после долгих await). */
  saveBlocksExplicit: (
    targetPageId: number,
    blocksToSave: TextBlock[],
    refreshSpeakers?: boolean
  ) => Promise<void>
  /** Помечает страницу грязной и инкрементирует ревизию правок. */
  markDirty: () => void
  /** Проверяет, что страница всё ещё открыта в редакторе. */
  isCurrentPage: (pageId: number) => boolean
  /** Обновляет UI-стейт блоков, только если страница всё ещё открыта. */
  applyBlocksForPage: (pageId: number, next: TextBlock[]) => void
  recordCleanAction: () => void
  discardLastSnapshot: () => void
  onPageStatusUpdate: (pageId: number, status: PageStatus, cleanPath?: string) => void
  setShowTypeset: (show: boolean) => void
  setViewMode: (mode: "original" | "clean") => void
  cleanCacheBuster: number

  setIsDetecting: (value: boolean) => void
  setIsOcrRunning: (value: boolean) => void
  setIsBatchTranslating: (value: boolean) => void
  setIsCleaning: (value: boolean) => void
  setIsRevertingClean: (value: boolean) => void
  setIsFullAuto: (value: boolean) => void
  setIsExporting: (value: boolean) => void
  setIsExportSuccess: (value: boolean) => void
}

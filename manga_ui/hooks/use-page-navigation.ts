// manga_ui/hooks/use-page-navigation.ts
// Переключение страниц главы: выбор страницы, предыдущая/следующая, защита от гонок и Stale Closure

import { useRef, useCallback } from "react"
import type { PageItem, PageStatus, TextBlock, TitleSettings } from "@/lib/types"
import { insertBlockInMangaOrder, mapDbBlockToTextBlock } from "@/lib/typeset"
import { getPageDetails, getPageBlocks, runPageAutoDetect } from "@/lib/api"

export interface UsePageNavigationProps {
  currentPage: PageItem | null
  chapterPages: PageItem[]
  setCurrentPage: React.Dispatch<React.SetStateAction<PageItem | null>>
  setChapterPages: React.Dispatch<React.SetStateAction<PageItem[]>>
  setCurrentTitleId: (titleId: number) => void
  setTitleFontSize?: (size: number) => void
  setIsDetecting?: (isDetecting: boolean) => void
  setViewMode: (mode: "original" | "clean") => void
  setCleanCacheBuster: (value: number) => void
  globalSettings: TitleSettings
  saveBlocksExplicit: (targetPageId: number, blocksToSave: TextBlock[], refreshSpeakers?: boolean) => Promise<void>
  isDirtyRef: React.MutableRefObject<boolean>
  textBlocksRef: React.MutableRefObject<TextBlock[]>
  clearBlocks: () => void
  setNewPageBlocks: (newBlocks: TextBlock[]) => void
  setSelectedId: (id: string | null) => void
  onPageStatusUpdate: (pageId: number, status: PageStatus, cleanPath?: string) => void
  onRefreshSpeakers: (pageId: number) => Promise<void>
}

export interface UsePageNavigationReturn {
  handleSelectPage: (page: PageItem, skipSave?: boolean, chapterPages?: PageItem[]) => Promise<void>
  handlePrevPage: () => Promise<void>
  handleNextPage: () => Promise<void>
  currentPageIdx: number
}

export function usePageNavigation({
  currentPage,
  chapterPages,
  setCurrentPage,
  setChapterPages,
  setCurrentTitleId,
  setTitleFontSize,
  setIsDetecting,
  setViewMode,
  setCleanCacheBuster,
  globalSettings,
  saveBlocksExplicit,
  isDirtyRef,
  textBlocksRef,
  clearBlocks,
  setNewPageBlocks,
  setSelectedId,
  onPageStatusUpdate,
  onRefreshSpeakers,
}: UsePageNavigationProps): UsePageNavigationReturn {
  const chapterPagesRef = useRef<PageItem[]>([])
  chapterPagesRef.current = chapterPages

  const currentPageRef = useRef<PageItem | null>(currentPage)
  currentPageRef.current = currentPage

  const globalSettingsRef = useRef<TitleSettings>(globalSettings)
  globalSettingsRef.current = globalSettings

  const isSwitchingPageRef = useRef(false)

  const currentPageIdx = chapterPages.findIndex((p) => p.id === currentPage?.id)

  const handleSelectPage = useCallback(
    async (page: PageItem, skipSave = false, nextChapterPages?: PageItem[]) => {
      if (isSwitchingPageRef.current) return
      isSwitchingPageRef.current = true

      try {
        // Список страниц новой главы переключаем только после защиты от гонки:
        // иначе шапка и пакетные действия уедут на другую главу, а на экране
        // останется страница старой.
        if (nextChapterPages) {
          setChapterPages(nextChapterPages)
        }

        const prevPage = currentPageRef.current
        if (!skipSave && prevPage && isDirtyRef.current) {
          try {
            await saveBlocksExplicit(prevPage.id, textBlocksRef.current, false)
          } catch (e) {
            console.warn("Не удалось сохранить предыдущую страницу:", e)
          }
        }

        clearBlocks()

        const freshPage = (await getPageDetails(page.id)) || page
        setCurrentPage(freshPage)
        currentPageRef.current = freshPage

        if (freshPage.title_id) {
          setCurrentTitleId(freshPage.title_id)
        }
        if (freshPage.default_font_size && setTitleFontSize) {
          setTitleFontSize(freshPage.default_font_size)
        }

        setViewMode(freshPage.clean_path ? "clean" : "original")
        setCleanCacheBuster(Date.now())
        onRefreshSpeakers(freshPage.id)

        const dbBlocks = await getPageBlocks(page.id)

        if (dbBlocks && dbBlocks.length > 0) {
          const loaded: TextBlock[] = dbBlocks.map((b: any) => mapDbBlockToTextBlock(b))
          setNewPageBlocks(loaded)
          setSelectedId(loaded[0]?.id || null)
        } else {
          const isFreshPage = freshPage.status === "raw" || freshPage.status === "new"
          if (isFreshPage) {
            const activeSettings = globalSettingsRef.current
            setIsDetecting?.(true)
            try {
              const detectRes = await runPageAutoDetect(
                page.id,
                activeSettings.detect_conf,
                false
              )
              // Упавший детект не должен помечать raw-страницу как detected.
              if (!detectRes || detectRes.success === false) {
                throw new Error(detectRes?.error || "Ошибка детекции")
              }
              const detectedBoxes: TextBlock[] = (detectRes?.boxes || []).map((box: any) => {
                const mapped = mapDbBlockToTextBlock(box)
                return {
                  ...mapped,
                  id: box.id !== undefined && box.id !== null ? mapped.id : crypto.randomUUID(),
                  fontFamily: box.font_family || activeSettings.font_bubble || mapped.fontFamily,
                  paddingMode:
                    (box.padding_mode as TextBlock["paddingMode"]) ||
                    activeSettings.default_padding ||
                    mapped.paddingMode,
                  minHyphens:
                    box.min_hyphens !== undefined
                      ? Boolean(box.min_hyphens)
                      : (activeSettings.default_hyphenation ?? mapped.minHyphens),
                }
              })

              // Защита от затирания: если пользователь успел нарисовать рамки во время авто-детекта,
              // сохраняем пользовательские рамки вместе с найденными
              const userAddedWhileDetecting = textBlocksRef.current
              if (userAddedWhileDetecting.length > 0) {
                // Вставляем пользовательские рамки по одной, чтобы сохранить
                // умный порядок чтения gutter_cutter, а не пересортировывать всё заново.
                let merged = detectedBoxes
                for (const userBlock of userAddedWhileDetecting) {
                  merged = insertBlockInMangaOrder(merged, userBlock)
                }
                setNewPageBlocks(merged)
                isDirtyRef.current = true
                await saveBlocksExplicit(page.id, merged, false)
              } else {
                setNewPageBlocks(detectedBoxes)
                if (detectedBoxes[0]) setSelectedId(detectedBoxes[0].id)
              }
              onPageStatusUpdate(
                page.id,
                ((detectRes as any)?.page_status as PageStatus) || "detected"
              )
            } finally {
              setIsDetecting?.(false)
            }
          } else {
            setNewPageBlocks([])
          }
        }
      } catch (e) {
        console.error("Ошибка при переключении страницы:", e)
        setNewPageBlocks([])
      } finally {
        isSwitchingPageRef.current = false
      }
    },
    [
      clearBlocks,
      isDirtyRef,
      onPageStatusUpdate,
      onRefreshSpeakers,
      saveBlocksExplicit,
      setCleanCacheBuster,
      setCurrentPage,
      setChapterPages,
      setCurrentTitleId,
      setIsDetecting,
      setNewPageBlocks,
      setSelectedId,
      setTitleFontSize,
      setViewMode,
      textBlocksRef,
    ]
  )

  const handlePrevPage = useCallback(async () => {
    const pages = chapterPagesRef.current
    const idx = pages.findIndex((p) => p.id === currentPageRef.current?.id)
    if (idx > 0) {
      const prev = pages[idx - 1]
      if (prev) await handleSelectPage(prev, false)
    }
  }, [handleSelectPage])

  const handleNextPage = useCallback(async () => {
    const pages = chapterPagesRef.current
    const idx = pages.findIndex((p) => p.id === currentPageRef.current?.id)
    if (idx >= 0 && idx < pages.length - 1) {
      const next = pages[idx + 1]
      if (next) await handleSelectPage(next, false)
    }
  }, [handleSelectPage])

  return { handleSelectPage, handlePrevPage, handleNextPage, currentPageIdx }
}

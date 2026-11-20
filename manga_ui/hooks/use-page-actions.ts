// manga_ui/hooks/use-page-actions.ts
// Действия над текущей страницей: кисть, OCR одного блока, смена класса бабла

import { useCallback } from "react"
import type { PageItem, PageStatus, TextBlock, TitleSettings } from "@/lib/types"
import { resetChapterBubbleFonts, runBrushClean, runOcr } from "@/lib/api"
import type { BrushMaskRect } from "@/lib/api/pages"

export interface UsePageActionsProps {
  currentPage: PageItem | null
  chapterPages: PageItem[]
  titleFontSize: number
  globalSettings: TitleSettings
  selectedId: string | null
  textBlocksRef: React.MutableRefObject<TextBlock[]>
  saveBlocks: (refreshSpeakers?: boolean) => Promise<void>
  isCurrentPage: (pageId: number) => boolean
  updateBlock: (id: string, patch: Partial<TextBlock>) => void
  setTextBlocks: React.Dispatch<React.SetStateAction<TextBlock[]>>
  setViewMode: React.Dispatch<React.SetStateAction<"original" | "clean">>
  setCleanCacheBuster: (value: number) => void
  setShowTypeset: React.Dispatch<React.SetStateAction<boolean>>
  setShowJapOverlay: React.Dispatch<React.SetStateAction<boolean>>
  setBrushSize: React.Dispatch<React.SetStateAction<number>>
  setIsApplyingChapterFont: React.Dispatch<React.SetStateAction<boolean>>
  recordCleanAction: () => void
  discardLastSnapshot: () => void
  handlePageStatusUpdate: (pageId: number, status: PageStatus, cleanPath?: string) => void
}

export interface UsePageActionsReturn {
  handleBrushClean: (
    maskBase64: string,
    mode?: "lama" | "white" | "black",
    maskRect?: BrushMaskRect
  ) => Promise<void>
  handleOcrSingleBlock: (block: TextBlock) => Promise<void>
  handleSetBlockClass: (classId: number) => void
  handleApplyFontSizeToChapter: () => Promise<void>
  handleBrushResize: (delta: number) => void
  handleToggleViewMode: () => void
  handleToggleTypeset: () => void
  handleToggleJapOverlay: () => void
}

export function usePageActions({
  currentPage,
  chapterPages,
  titleFontSize,
  globalSettings,
  selectedId,
  textBlocksRef,
  saveBlocks,
  isCurrentPage,
  updateBlock,
  setTextBlocks,
  setViewMode,
  setCleanCacheBuster,
  setShowTypeset,
  setShowJapOverlay,
  setBrushSize,
  setIsApplyingChapterFont,
  recordCleanAction,
  discardLastSnapshot,
  handlePageStatusUpdate,
}: UsePageActionsProps): UsePageActionsReturn {
  const handleBrushClean = useCallback(
    async (
      maskBase64: string,
      mode: "lama" | "white" | "black" = "lama",
      maskRect?: BrushMaskRect
    ) => {
      if (!currentPage) return
      const targetPageId = currentPage.id
      try {
        recordCleanAction()
        const res = await runBrushClean(targetPageId, maskBase64, mode, maskRect)
        if (res.success) {
          handlePageStatusUpdate(targetPageId, res.page_status || "cleaned", res.clean_path)
          // UI-мутации — только если пользователь не переключил страницу.
          if (isCurrentPage(targetPageId)) {
            setViewMode("clean")
            setCleanCacheBuster(Date.now())
          }
        } else {
          if (isCurrentPage(targetPageId)) discardLastSnapshot()
          alert("Ошибка кисти: " + (res.error || "Неизвестная ошибка"))
        }
      } catch (e) {
        if (isCurrentPage(targetPageId)) discardLastSnapshot()
        console.error("Ошибка применения кисти:", e)
        alert("Ошибка кисти: " + String(e))
      }
    },
    [currentPage, isCurrentPage, handlePageStatusUpdate, recordCleanAction, discardLastSnapshot, setViewMode, setCleanCacheBuster]
  )

  const handleOcrSingleBlock = useCallback(
    async (block: TextBlock) => {
      if (!currentPage) return
      const targetPageId = currentPage.id
      try {
        const text = await runOcr(
          targetPageId,
          block.x,
          block.y,
          block.width,
          block.height,
          block.rotation || 0,
          block.id,
          block.class_id ?? 0
        )
        // Не трогаем UI, если пользователь уже переключил страницу.
        if (!isCurrentPage(targetPageId)) return
        updateBlock(block.id, {
          japText: text,
          status: block.status === "translated" ? "translated" : "ocr-done",
        })
      } catch (e) {
        console.error("Ошибка OCR блока:", e)
        alert("OCR не удался: " + String(e))
      }
    },
    [currentPage, isCurrentPage, updateBlock]
  )

  const handleSetBlockClass = useCallback(
    (classId: number) => {
      if (!selectedId) return
      const targetBlock = textBlocksRef.current.find((b) => b.id === selectedId)
      const hasTranslation = Boolean(targetBlock?.rusText && targetBlock.rusText.trim())
      const autoOval = globalSettings.auto_oval_bubble ?? true
      const shape = classId === 0 && autoOval && hasTranslation ? "ellipse" : "rect"

      let fontFamily = globalSettings.font_bubble || "v_CCFaceFront"
      if (classId === 1) fontFamily = globalSettings.font_thought || "v_CCFaceFront"
      if (classId === 2 || classId === 3) fontFamily = globalSettings.font_sfx || "v_Mighty Zeo 2.0"

      updateBlock(selectedId, { class_id: classId, shape, fontFamily })
    },
    [selectedId, globalSettings, updateBlock, textBlocksRef]
  )

  const handleApplyFontSizeToChapter = useCallback(async () => {
    const chId = currentPage?.chapter_id || chapterPages[0]?.chapter_id
    if (!chId) return
    const targetPageId = currentPage?.id

    const ok = confirm(`Сбросить все баблы текущей главы в режим Auto под кегль ${titleFontSize}px?`)
    if (!ok) return

    setIsApplyingChapterFont(true)
    try {
      // Сохраняем текущую страницу до сброса кеглей в БД, чтобы не потерять
      // несохранённые текстовые правки.
      await saveBlocks()
      await resetChapterBubbleFonts(chId)
      // Если пользователь переключился на другую страницу/главу, не трогаем
      // её блоки в памяти — в БД сброс уже применён к целевой главе.
      if (targetPageId != null && !isCurrentPage(targetPageId)) {
        alert(`Все баблы главы успешно переведены в режим Auto (${titleFontSize}px)!`)
        return
      }
      const next = textBlocksRef.current.map((b) => ({ ...b, fontSize: undefined }))
      textBlocksRef.current = next
      setTextBlocks(next)
      alert(`Все баблы главы успешно переведены в режим Auto (${titleFontSize}px)!`)
    } catch (err) {
      alert("Ошибка применения к главе: " + String(err))
    } finally {
      setIsApplyingChapterFont(false)
    }
  }, [currentPage?.chapter_id, currentPage?.id, chapterPages, titleFontSize, saveBlocks, isCurrentPage, textBlocksRef, setTextBlocks, setIsApplyingChapterFont])

  const handleBrushResize = useCallback((delta: number) => {
    setBrushSize((prev) => Math.max(6, Math.min(160, prev + delta)))
  }, [setBrushSize])

  const handleToggleViewMode = useCallback(() => {
    if (currentPage?.clean_path) {
      setViewMode((prev) => (prev === "original" ? "clean" : "original"))
    }
  }, [currentPage?.clean_path, setViewMode])

  const handleToggleTypeset = useCallback(() => {
    setShowTypeset((prev) => !prev)
  }, [setShowTypeset])

  const handleToggleJapOverlay = useCallback(() => {
    setShowJapOverlay((prev) => !prev)
  }, [setShowJapOverlay])

  return {
    handleBrushClean,
    handleOcrSingleBlock,
    handleSetBlockClass,
    handleApplyFontSizeToChapter,
    handleBrushResize,
    handleToggleViewMode,
    handleToggleTypeset,
    handleToggleJapOverlay,
  }
}

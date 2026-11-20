"use client"

// manga_ui/components/manga-translator.tsx
/**
 * Корневой компонент-оркестратор рабочего пространства Manga Translator.
 *
 *
 * Управляемые стейты:
 * - currentPage, chapterPages, viewMode ('original' | 'clean'), cleanCacheBuster
 * - panelWidth (изменяемый сплиттером размер правой панели), isResizing
 * - globalSettings (настройки моделей, формы бабла, шрифтов, LaMa)
 * - titleFontSize (базовый кегль текущего тайтла)
 * - модальные окна: hotkeysModal, settingsModal
 *
 */

import { useState, useCallback, useMemo } from "react"
import type { PageItem } from "@/lib/types"
import { ImageViewer } from "@/components/image-viewer"
import { Sidebar } from "@/components/sidebar"
import { BatchChapterActions, type BatchAction } from "@/components/batch-chapter-actions"
import { TranslatorHeader } from "@/components/translator-header"
import { TranslationToolbar } from "@/components/translation-toolbar"
import { TextBlocksList } from "@/components/text-blocks-list"
import { HotkeysModal } from "@/components/hotkeys-modal"
import { SettingsModal } from "@/components/settings-modal"
import { StatisticsModal } from "@/components/statistics-modal"
import { openTranslatedFolder, getPageImageUrl, getPageCleanImageUrl, unloadAllModels } from "@/lib/api"
import { useMangaHotkeys } from "@/hooks/use-manga-hotkeys"
import { usePageBlocks } from "@/hooks/use-page-blocks"
import { usePagePipelines } from "@/hooks/use-page-pipelines"
import { usePanelResize } from "@/hooks/use-panel-resize"
import { usePageNavigation } from "@/hooks/use-page-navigation"
import { useMangaSettings } from "@/hooks/use-manga-settings"
import { useMangaPageState } from "@/hooks/use-manga-page-state"
import { usePageActions } from "@/hooks/use-page-actions"
import { useBatchChapterActions } from "@/hooks/use-batch-chapter-actions"
import { useUiLayerOpen } from "@/lib/ui-layer-store"
import { useUnsavedGuard } from "@/hooks/use-unsaved-guard"

export interface MangaTranslatorProps {}

export function MangaTranslator(_props: MangaTranslatorProps) {
  const [currentPage, setCurrentPage] = useState<PageItem | null>(null)
  const [chapterPages, setChapterPages] = useState<PageItem[]>([])
  const [viewMode, setViewMode] = useState<"original" | "clean">("original")
  const [cleanCacheBuster, setCleanCacheBuster] = useState<number>(Date.now())
  const [showTypeset, setShowTypeset] = useState(false)
  const [showJapOverlay, setShowJapOverlay] = useState(false)
  const [brushSize, setBrushSize] = useState<number>(32)
  const [sidebarRefreshTrigger, setSidebarRefreshTrigger] = useState(0)

  // Модальные окна
  const [showHotkeysModal, setShowHotkeysModal] = useState(false)
  const [showSettingsModal, setShowSettingsModal] = useState(false)
  const [showStatisticsModal, setShowStatisticsModal] = useState(false)

  // Полная выгрузка моделей из VRAM/RAM (кнопка в шапке)
  const [isUnloadingModels, setIsUnloadingModels] = useState(false)
  const [unloadMessage, setUnloadMessage] = useState<string | null>(null)

  const handleUnloadModels = useCallback(async () => {
    if (isUnloadingModels) return
    setIsUnloadingModels(true)
    setUnloadMessage(null)
    try {
      const res = await unloadAllModels()
      if (!res?.success) throw new Error(res?.error || "Ошибка выгрузки")
      const freed = res.freed_mb ?? 0
      setUnloadMessage(freed > 0 ? `Освобождено: ${Math.round(freed)} МБ` : "Память очищена")
    } catch (err) {
      console.warn("Не удалось выгрузить модели:", err)
      setUnloadMessage("Ошибка очистки")
    } finally {
      setIsUnloadingModels(false)
      setTimeout(() => setUnloadMessage(null), 2500)
    }
  }, [isUnloadingModels])

  const currentChapterId = currentPage?.chapter_id || chapterPages[0]?.chapter_id || null

  const { panelWidth, isResizing, startResizing } = usePanelResize()
  const settings = useMangaSettings()
  const pageState = useMangaPageState({
    setCurrentPage,
    setChapterPages,
    setViewMode,
    setCleanCacheBuster,
    currentPageId: currentPage?.id ?? null,
  })

  // Глобальные настройки с базовым кеглем текущего тайтла. useMemo сохраняет
  // ссылочную стабильность, иначе React.memo карточек не работает.
  const globalSettings = useMemo(
    () => ({ ...settings.globalSettings, default_font_size: settings.titleFontSize }),
    [settings.globalSettings, settings.titleFontSize]
  )

  const blocks = usePageBlocks(
    currentPage,
    globalSettings,
    pageState.handlePageStatusUpdate,
    pageState.refreshSpeakersList
  )

  useUnsavedGuard({
    isDirtyRef: blocks.isDirtyRef,
    currentPageRef: blocks.currentPageRef,
    textBlocksRef: blocks.textBlocksRef,
  })

  const pipelines = usePagePipelines({
    currentPage,
    setCurrentPage,
    textBlocks: blocks.textBlocks,
    setTextBlocks: blocks.setTextBlocks,
    textBlocksRef: blocks.textBlocksRef,
    globalSettings,
    setSelectedId: blocks.setSelectedId,
    saveBlocks: blocks.saveBlocks,
    saveBlocksExplicit: blocks.saveBlocksExplicit,
    markDirty: blocks.markDirty,
    isCurrentPage: blocks.isCurrentPage,
    applyBlocksForPage: blocks.applyBlocksForPage,
    recordCleanAction: blocks.recordCleanAction,
    discardLastSnapshot: blocks.discardLastSnapshot,
    onPageStatusUpdate: pageState.handlePageStatusUpdate,
    setShowTypeset,
    setViewMode,
    cleanCacheBuster,
  })

  const navigation = usePageNavigation({
    currentPage,
    chapterPages,
    setCurrentPage,
    setChapterPages,
    setCurrentTitleId: settings.setCurrentTitleId,
    setTitleFontSize: settings.setTitleFontSize,
    setIsDetecting: pipelines.setIsDetecting,
    setViewMode,
    setCleanCacheBuster,
    globalSettings,
    saveBlocksExplicit: blocks.saveBlocksExplicit,
    isDirtyRef: blocks.isDirtyRef,
    textBlocksRef: blocks.textBlocksRef,
    clearBlocks: blocks.clearBlocks,
    setNewPageBlocks: blocks.setNewPageBlocks,
    setSelectedId: blocks.setSelectedId,
    onPageStatusUpdate: pageState.handlePageStatusUpdate,
    onRefreshSpeakers: pageState.refreshSpeakersList,
  })

  const actions = usePageActions({
    currentPage,
    chapterPages,
    titleFontSize: settings.titleFontSize,
    globalSettings,
    selectedId: blocks.selectedId,
    textBlocksRef: blocks.textBlocksRef,
    saveBlocks: blocks.saveBlocks,
    isCurrentPage: blocks.isCurrentPage,
    updateBlock: blocks.updateBlock,
    setTextBlocks: blocks.setTextBlocks,
    setViewMode,
    setCleanCacheBuster,
    setShowTypeset,
    setShowJapOverlay,
    setBrushSize,
    setIsApplyingChapterFont: settings.setIsApplyingChapterFont,
    recordCleanAction: blocks.recordCleanAction,
    discardLastSnapshot: blocks.discardLastSnapshot,
    handlePageStatusUpdate: pageState.handlePageStatusUpdate,
  })

  const handleChapterDeleted = useCallback((deletedChapterId: number) => {
    // Глава может быть активной и без открытой страницы (chapterPages[0]).
    const activeChapterId = currentPage?.chapter_id ?? chapterPages[0]?.chapter_id
    if (activeChapterId === deletedChapterId) {
      blocks.clearBlocks()
      setCurrentPage(null)
      setChapterPages([])
    }
  }, [currentPage?.chapter_id, chapterPages, blocks.clearBlocks])

  const handleTitleDeleted = useCallback((deletedTitleId: number) => {
    // Открытая страница и выбранный в сайдбаре тайтл могут относиться
    // к разным тайтлам — очищаем их независимо.
    if (currentPage?.title_id === deletedTitleId) {
      blocks.clearBlocks()
      setCurrentPage(null)
      setChapterPages([])
    }
    if (settings.currentTitleId === deletedTitleId) {
      settings.setCurrentTitleId(null)
    }
  }, [
    currentPage?.title_id,
    settings.currentTitleId,
    settings.setCurrentTitleId,
    blocks.clearBlocks,
  ])

  // Стабильные обработчики перемещения: inline-стрелки в пропсах отключали
  // React.memo у каждой карточки бабла.
  const handleMoveBlockUp = useCallback(
    (id: string) => blocks.moveBlock(id, "up"),
    [blocks.moveBlock]
  )
  const handleMoveBlockDown = useCallback(
    (id: string) => blocks.moveBlock(id, "down"),
    [blocks.moveBlock]
  )

  // Пакетные действия главы подняты в родителя: одни и те же обработчики
  // используются панелью <BatchChapterActions /> и глобальными хоткеями (Alt+D/C/E/J/I).
  const batchChapterProps = {
    pages: chapterPages,
    currentPageId: currentPage?.id ?? null,
    titleDefaultFontSize: settings.titleFontSize,
    onSaveCurrentPage: () => blocks.saveBlocks(true),
    onPageStatusUpdate: pageState.handlePageStatusUpdate,
    onCompleteBatch: () => setSidebarRefreshTrigger((prev) => prev + 1),
    onRefreshCurrent: (action?: BatchAction) => {
      // Clean / Export / Script-Export не меняют text_blocks в БД — перезагружать
      // текущую страницу и сбрасывать правки не нужно (clean_path уже обновлён).
      if (action === "clean" || action === "export" || action === "script-export") return
      const activePage = blocks.currentPageRef.current
      if (!activePage) return
      // Не затираем несохранённые правки пользователя на открытой странице.
      if (blocks.isDirtyRef.current) return
      void navigation.handleSelectPage(activePage, true)
    },
  }

  const batchActions = useBatchChapterActions(batchChapterProps)

  const uiLayerOpen = useUiLayerOpen()

  useMangaHotkeys({
    disabled: uiLayerOpen,
    selectedId: blocks.selectedId,
    textBlocks: blocks.textBlocks,
    defaultFontSize: settings.titleFontSize,
    onPrevPage: navigation.handlePrevPage,
    onNextPage: navigation.handleNextPage,
    onSave: () => blocks.saveBlocks(true),
    onUndo: blocks.undo,
    onRedo: blocks.redo,
    onToggleViewMode: actions.handleToggleViewMode,
    onToggleTypeset: actions.handleToggleTypeset,
    onToggleJapCheck: actions.handleToggleJapOverlay,
    onOcrBlock: actions.handleOcrSingleBlock,
    onSetClass: actions.handleSetBlockClass,
    onDeleteBlock: blocks.deleteBlock,
    onMoveBlock: blocks.moveBlock,
    onUpdateBlock: blocks.updateBlock,
    onCleanPage: () => void pipelines.handleCleanPage("auto"),
    onSpotClean: blocks.spotCleanBlock,
    onBrushResize: actions.handleBrushResize,
    onChapterDetectAll: batchActions.detectAll,
    onChapterCleanAll: batchActions.cleanChapter,
    onChapterExportAll: batchActions.exportAll,
    onChapterExportJson: batchActions.handleExportScript,
    onChapterImportJson: batchActions.handleImportClick,
  })

  const currentSpeakers = blocks.textBlocks.map((b) => b.speaker?.trim()).filter((s): s is string => !!s)
  const allSpeakerSuggestions = Array.from(new Set([...pageState.knownSpeakers, ...currentSpeakers])).sort()

  const activeImageSrc = currentPage
    ? viewMode === "clean" && currentPage.clean_path
      ? `${getPageCleanImageUrl(currentPage.id)}?t=${cleanCacheBuster}`
      : getPageImageUrl(currentPage.id)
    : null

  return (
    <div className={`flex h-screen flex-col bg-slate-900 text-slate-100 ${isResizing ? "select-none" : ""}`}>
      <datalist id="manga-speakers">
        {allSpeakerSuggestions.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>

      <TranslatorHeader
        currentPage={currentPage}
        currentIndex={navigation.currentPageIdx}
        totalPages={chapterPages.length}
        currentChapterId={currentChapterId}
        titleFontSize={settings.titleFontSize}
        onTitleFontSizeChange={settings.handleTitleFontSizeChange}
        onApplyFontSizeToChapter={actions.handleApplyFontSizeToChapter}
        isApplyingChapterFont={settings.isApplyingChapterFont}
        isSaving={blocks.isSaving}
        isExporting={pipelines.isExporting}
        isExportSuccess={pipelines.isExportSuccess}
        isUnloadingModels={isUnloadingModels}
        unloadMessage={unloadMessage}
        onUnloadModels={handleUnloadModels}
        onOpenFolder={() => currentPage && openTranslatedFolder(currentPage.id)}
        onExportPage={pipelines.handleExportPage}
        onSaveBlocks={() => blocks.saveBlocks(true)}
        onPrevPage={navigation.handlePrevPage}
        onNextPage={navigation.handleNextPage}
        onOpenHotkeys={() => setShowHotkeysModal(true)}
        onOpenSettings={() => setShowSettingsModal(true)}
        onOpenStatistics={() => setShowStatisticsModal(true)}
      />

      <BatchChapterActions {...batchChapterProps} controller={batchActions} />

      <div className="flex min-h-0 flex-1 overflow-hidden relative">
        <Sidebar
          currentPageId={currentPage?.id || null}
          activePageUpdate={pageState.activePageUpdate}
          refreshTrigger={sidebarRefreshTrigger}
          onSelectPage={(page, pages) => navigation.handleSelectPage(page, false, pages)}
          onChapterDeleted={handleChapterDeleted}
          onTitleSelected={settings.handleTitleSelected}
          onTitleDeleted={handleTitleDeleted}
        />

        <ImageViewer
          imageSrc={activeImageSrc}
          textBlocks={blocks.textBlocks}
          selectedId={blocks.selectedId}
          titleId={currentPage?.title_id ?? settings.currentTitleId}
          showTypeset={showTypeset}
          showJapOverlay={showJapOverlay}
          pageNumber={currentPage?.page_number}
          hasCleanScan={Boolean(currentPage?.clean_path)}
          viewMode={viewMode}
          defaultFontSize={settings.titleFontSize}
          autoOvalBubble={settings.globalSettings.auto_oval_bubble ?? true}
          brushSize={brushSize}
          onBrushResize={actions.handleBrushResize}
          onToggleViewMode={actions.handleToggleViewMode}
          onSelect={blocks.setSelectedId}
          onDrawComplete={blocks.addOrUpdateDrawnBlock}
          onUpdateBlock={blocks.updateBlock}
          onUpdateBlockTransient={blocks.updateBlockTransient}
          getHistoryDepth={blocks.getHistoryDepth}
          onTruncateHistory={blocks.truncateHistory}
          onBrushClean={actions.handleBrushClean}
        />

        <div
          onMouseDown={startResizing}
          className={[
            "w-1.5 shrink-0 cursor-col-resize select-none transition-colors relative z-30 group",
            isResizing ? "bg-indigo-500" : "bg-slate-800 hover:bg-indigo-500/70",
          ].join(" ")}
          title="Потяните, чтобы изменить ширину правой панели"
        >
          <div className="absolute inset-y-0 -left-1 -right-1" />
        </div>

        <section
          style={{ width: `${panelWidth}px` }}
          className="flex min-h-0 shrink-0 flex-col overflow-hidden bg-slate-950/60"
        >
          <TranslationToolbar
            hasCurrentPage={Boolean(currentPage)}
            hasBlocks={blocks.textBlocks.length > 0}
            hasCleanScan={Boolean(currentPage?.clean_path)}
            isFullAuto={pipelines.isFullAuto}
            isDetecting={pipelines.isDetecting}
            isOcrRunning={pipelines.isOcrRunning}
            isBatchTranslating={pipelines.isBatchTranslating}
            isCleaning={pipelines.isCleaning}
            isRevertingClean={pipelines.isRevertingClean}
            showTypeset={showTypeset}
            showJapOverlay={showJapOverlay}
            onFullAuto={pipelines.handleFullAuto}
            onAutoDetect={pipelines.handleAutoDetect}
            onOcrAllBlocks={pipelines.handleOcrAllBlocks}
            onTranslateAll={pipelines.handleTranslateAll}
            onCleanPage={pipelines.handleCleanPage}
            onRevertClean={pipelines.handleRevertClean}
            onToggleTypeset={actions.handleToggleTypeset}
            onToggleJapOverlay={actions.handleToggleJapOverlay}
          />

          <TextBlocksList
            currentPage={currentPage}
            textBlocks={blocks.textBlocks}
            selectedId={blocks.selectedId}
            titleId={currentPage?.title_id ?? settings.currentTitleId}
            showJapOverlay={showJapOverlay}
            defaultFontSize={settings.titleFontSize}
            autoOvalBubble={settings.globalSettings.auto_oval_bubble ?? true}
            fontBubble={settings.globalSettings.font_bubble}
            fontThought={settings.globalSettings.font_thought}
            fontSfx={settings.globalSettings.font_sfx}
            onSelect={blocks.setSelectedId}
            onUpdate={blocks.updateBlock}
            onDelete={blocks.deleteBlock}
            onMoveUp={handleMoveBlockUp}
            onMoveDown={handleMoveBlockDown}
            onSpotClean={blocks.spotCleanBlock}
          />
        </section>
      </div>

      {showHotkeysModal && <HotkeysModal onClose={() => setShowHotkeysModal(false)} />}

      {showSettingsModal && (
        <SettingsModal
          onClose={() => setShowSettingsModal(false)}
          onSettingsUpdated={(newSettings) => {
            settings.setGlobalSettings((prev) => ({ ...prev, ...newSettings }))
          }}
        />
      )}

      {showStatisticsModal && (
        <StatisticsModal
          currentChapterId={currentChapterId}
          onClose={() => setShowStatisticsModal(false)}
        />
      )}
    </div>
  )
}

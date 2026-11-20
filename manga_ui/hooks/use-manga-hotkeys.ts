// manga_ui/hooks/use-manga-hotkeys.ts
/**
 * Хуки конфигурации горячих клавиш и глобальной диспетчеризации нажатий.
 * Глобальный слушатель хоткеев с поддержкой Undo/Redo (Ctrl+Z / Ctrl+Y),
 * одиночного OCR [O], проверки японского текста [J] и операций со страницей.
 * Диспетчеризация нажатий вынесена в hotkey-dispatcher.ts
 */

import { useEffect, useRef } from "react"
import type { TextBlock } from "@/lib/types"
import { useHotkeysConfig } from "@/lib/hotkeys-store"
import { dispatchMangaHotkey } from "./hotkey-dispatcher"

export { useHotkeysConfig }
export type { UseHotkeysConfigReturn } from "@/lib/hotkeys-store"

export interface UseMangaHotkeysProps {
  /** true, когда открыта модалка: фоновые хоткеи не обрабатываются. */
  disabled?: boolean
  selectedId: string | null
  textBlocks: TextBlock[]
  defaultFontSize?: number
  onPrevPage: () => void
  onNextPage: () => void
  onSave: () => void
  onUndo?: () => Promise<void> | void
  onRedo?: () => Promise<void> | void
  onToggleViewMode?: () => void
  onToggleTypeset?: () => void
  onToggleJapCheck?: () => void
  onOcrBlock?: (block: TextBlock) => Promise<void> | void
  onSetClass?: (classId: number) => void
  onDeleteBlock: (id: string) => void
  onMoveBlock: (id: string, direction: "up" | "down") => void
  onUpdateBlock: (id: string, patch: Partial<TextBlock>) => void
  onCleanPage?: () => void
  onSpotClean?: (block: TextBlock, method: "auto" | "lama" | "white", deleteAfter?: boolean) => Promise<void>
  onBrushResize?: (delta: number) => void
  onChapterDetectAll?: () => void
  onChapterCleanAll?: () => void
  onChapterExportAll?: () => void
  onChapterExportJson?: () => void
  onChapterImportJson?: () => void
}

export function useMangaHotkeys(props: UseMangaHotkeysProps): void {
  const { hotkeys } = useHotkeysConfig()

  // Единственная подписка на window: актуальные пропсы и хоткеи читаем из ref,
  // чтобы не переподписываться на каждый рендер (и на каждый тик состояния).
  const propsRef = useRef(props)
  propsRef.current = props
  const hotkeysRef = useRef(hotkeys)
  hotkeysRef.current = hotkeys

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const p = propsRef.current
      dispatchMangaHotkey(e, {
        hotkeys: hotkeysRef.current,
        disabled: p.disabled,
        selectedId: p.selectedId,
        textBlocks: p.textBlocks,
        defaultFontSize: p.defaultFontSize ?? 14,
        onPrevPage: p.onPrevPage,
        onNextPage: p.onNextPage,
        onSave: p.onSave,
        onUndo: p.onUndo,
        onRedo: p.onRedo,
        onToggleViewMode: p.onToggleViewMode,
        onToggleTypeset: p.onToggleTypeset,
        onToggleJapCheck: p.onToggleJapCheck,
        onOcrBlock: p.onOcrBlock,
        onSetClass: p.onSetClass,
        onDeleteBlock: p.onDeleteBlock,
        onMoveBlock: p.onMoveBlock,
        onUpdateBlock: p.onUpdateBlock,
        onCleanPage: p.onCleanPage,
        onSpotClean: p.onSpotClean,
        onBrushResize: p.onBrushResize,
        onChapterDetectAll: p.onChapterDetectAll,
        onChapterCleanAll: p.onChapterCleanAll,
        onChapterExportAll: p.onChapterExportAll,
        onChapterExportJson: p.onChapterExportJson,
        onChapterImportJson: p.onChapterImportJson,
      })
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])
}

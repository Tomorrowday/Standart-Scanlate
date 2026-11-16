// manga_ui/hooks/use-manga-hotkeys.ts
/**
 * Хуки конфигурации горячих клавиш и глобальной диспетчеризации нажатий.
 * Глобальный слушатель хоткеев с поддержкой Undo/Redo (Ctrl+Z / Ctrl+Y),
 * одиночного OCR [O], проверки японского текста [J] и операций со страницей.
 * Диспетчеризация нажатий вынесена в hotkey-dispatcher.ts
 */

import { useEffect, useState, useCallback } from "react"
import type { TextBlock } from "@/lib/types"
import {
  type HotkeyConfig,
  type HotkeyActionId,
  DEFAULT_HOTKEYS,
  HOTKEYS_UPDATED_EVENT,
  loadHotkeys,
  saveHotkeys,
} from "@/lib/hotkeys"
import { dispatchMangaHotkey } from "./hotkey-dispatcher"

export interface UseHotkeysConfigReturn {
  hotkeys: HotkeyConfig
  updateHotkey: (action: HotkeyActionId, patch: Partial<HotkeyConfig[HotkeyActionId]>) => void
  resetHotkeys: () => void
}

export interface UseMangaHotkeysProps {
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
  onSpotClean?: (block: TextBlock, method: "auto" | "lama" | "white", deleteAfter?: boolean) => Promise<void>
  onBrushResize?: (delta: number) => void
  onChapterDetectAll?: () => void
  onChapterCleanAll?: () => void
  onChapterExportAll?: () => void
  onChapterExportJson?: () => void
  onChapterImportJson?: () => void
}

export function useHotkeysConfig(): UseHotkeysConfigReturn {
  const [hotkeys, setHotkeys] = useState<HotkeyConfig>(() => loadHotkeys())

  useEffect(() => {
    const sync = () => setHotkeys(loadHotkeys())
    window.addEventListener(HOTKEYS_UPDATED_EVENT, sync)
    window.addEventListener("storage", sync)
    return () => {
      window.removeEventListener(HOTKEYS_UPDATED_EVENT, sync)
      window.removeEventListener("storage", sync)
    }
  }, [])

  const updateHotkey = useCallback((action: HotkeyActionId, patch: Partial<HotkeyConfig[HotkeyActionId]>) => {
    setHotkeys((prev) => {
      const next = {
        ...prev,
        [action]: { ...prev[action], ...patch },
      }
      queueMicrotask(() => {
        saveHotkeys(next)
      })
      return next
    })
  }, [])

  const resetHotkeys = useCallback(() => {
    const next = { ...DEFAULT_HOTKEYS }
    setHotkeys(next)
    queueMicrotask(() => {
      saveHotkeys(next)
    })
  }, [])

  return { hotkeys, updateHotkey, resetHotkeys }
}

export function useMangaHotkeys(props: UseMangaHotkeysProps): void {
  const { hotkeys } = useHotkeysConfig()

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      dispatchMangaHotkey(e, {
        hotkeys,
        selectedId: props.selectedId,
        textBlocks: props.textBlocks,
        defaultFontSize: props.defaultFontSize ?? 14,
        onPrevPage: props.onPrevPage,
        onNextPage: props.onNextPage,
        onSave: props.onSave,
        onUndo: props.onUndo,
        onRedo: props.onRedo,
        onToggleViewMode: props.onToggleViewMode,
        onToggleTypeset: props.onToggleTypeset,
        onToggleJapCheck: props.onToggleJapCheck,
        onOcrBlock: props.onOcrBlock,
        onSetClass: props.onSetClass,
        onDeleteBlock: props.onDeleteBlock,
        onMoveBlock: props.onMoveBlock,
        onUpdateBlock: props.onUpdateBlock,
        onSpotClean: props.onSpotClean,
        onBrushResize: props.onBrushResize,
        onChapterDetectAll: props.onChapterDetectAll,
        onChapterCleanAll: props.onChapterCleanAll,
        onChapterExportAll: props.onChapterExportAll,
        onChapterExportJson: props.onChapterExportJson,
        onChapterImportJson: props.onChapterImportJson,
      })
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [
    hotkeys,
    props.selectedId,
    props.textBlocks,
    props.defaultFontSize,
    props.onPrevPage,
    props.onNextPage,
    props.onSave,
    props.onUndo,
    props.onRedo,
    props.onToggleViewMode,
    props.onToggleTypeset,
    props.onToggleJapCheck,
    props.onOcrBlock,
    props.onSetClass,
    props.onDeleteBlock,
    props.onMoveBlock,
    props.onUpdateBlock,
    props.onSpotClean,
    props.onBrushResize,
    props.onChapterDetectAll,
    props.onChapterCleanAll,
    props.onChapterExportAll,
    props.onChapterExportJson,
    props.onChapterImportJson,
  ])
}

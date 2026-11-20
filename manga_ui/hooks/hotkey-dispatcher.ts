// manga_ui/hooks/hotkey-dispatcher.ts
// Сопоставление и диспетчеризация глобальных горячих клавиш: Undo/Redo, навигация,
// OCR, классы баблов, шрифты, клин, порядок чтения и стили выделенного блока

import {
  type HotkeyConfig,
  type HotkeyActionId,
  matchHotkey,
  MANGA_FONTS,
} from "@/lib/hotkeys"
import type { TextBlock } from "@/lib/types"

export interface HotkeyDispatchContext {
  hotkeys: HotkeyConfig
  /** true, когда поверх страницы открыта модалка/другой UI-слой. */
  disabled?: boolean
  selectedId: string | null
  textBlocks: TextBlock[]
  defaultFontSize: number
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
  onToggleToolMode?: () => void
  onChapterDetectAll?: () => void
  onChapterCleanAll?: () => void
  onChapterExportAll?: () => void
  onChapterExportJson?: () => void
  onChapterImportJson?: () => void
}

/** Обрабатывает нажатие; возвращает true, если событие было перехвачено. */
export function dispatchMangaHotkey(e: KeyboardEvent, ctx: HotkeyDispatchContext): boolean {
  // Пока открыта модалка, фоновые хоткеи страницы не должны менять данные.
  if (ctx.disabled) return false

  const target = e.target as HTMLElement | null
  if (
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLSelectElement ||
    target?.isContentEditable
  ) {
    return false
  }

  const { hotkeys, selectedId, textBlocks, defaultFontSize } = ctx

  // 0. Undo / Redo (Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z)
  const isCtrlOrMeta = e.ctrlKey || e.metaKey
  if (
    matchHotkey(e, hotkeys.redoAction) ||
    (isCtrlOrMeta && e.shiftKey && !e.altKey && e.code === "KeyZ")
  ) {
    if (ctx.onRedo) {
      e.preventDefault()
      ctx.onRedo()
      return true
    }
  }
  if (matchHotkey(e, hotkeys.undoAction)) {
    if (ctx.onUndo) {
      e.preventDefault()
      ctx.onUndo()
      return true
    }
  }

  // 1. Навигация по страницам
  if (matchHotkey(e, hotkeys.prevPage) || e.code === "PageUp" || (e.altKey && e.code === "ArrowLeft")) {
    e.preventDefault()
    ctx.onPrevPage()
    return true
  }
  if (matchHotkey(e, hotkeys.nextPage) || e.code === "PageDown" || (e.altKey && e.code === "ArrowRight")) {
    e.preventDefault()
    ctx.onNextPage()
    return true
  }

  // 2. Сохранение страницы
  if (matchHotkey(e, hotkeys.savePage)) {
    e.preventDefault()
    ctx.onSave()
    return true
  }

  // 3. Переключение режима скана (Tab)
  if (matchHotkey(e, hotkeys.toggleViewMode)) {
    if (ctx.onToggleViewMode) {
      e.preventDefault()
      ctx.onToggleViewMode()
      return true
    }
  }

  // 4. Включение / выключение тайпсета (T)
  if (matchHotkey(e, hotkeys.toggleTypeset)) {
    if (ctx.onToggleTypeset) {
      e.preventDefault()
      ctx.onToggleTypeset()
      return true
    }
  }

  // 5. Включение / выключение японских плашек у баблов (J)
  if (matchHotkey(e, hotkeys.toggleJapCheck)) {
    if (ctx.onToggleJapCheck) {
      e.preventDefault()
      ctx.onToggleJapCheck()
      return true
    }
  }

  // 5.1. Переключение инструмента Box / Brush (V)
  if (matchHotkey(e, hotkeys.toggleToolMode)) {
    if (ctx.onToggleToolMode) {
      e.preventDefault()
      ctx.onToggleToolMode()
      return true
    }
  }

  // 6. Автоклин текущей страницы (Smart Clean)
  if (matchHotkey(e, hotkeys.cleanPage)) {
    if (ctx.onCleanPage) {
      e.preventDefault()
      ctx.onCleanPage()
      return true
    }
  }

  // 7. Действия с главой
  if (matchHotkey(e, hotkeys.chapterDetectAll)) {
    e.preventDefault()
    ctx.onChapterDetectAll?.()
    return true
  }
  if (matchHotkey(e, hotkeys.chapterCleanAll)) {
    e.preventDefault()
    ctx.onChapterCleanAll?.()
    return true
  }
  if (matchHotkey(e, hotkeys.chapterExportAll)) {
    e.preventDefault()
    ctx.onChapterExportAll?.()
    return true
  }
  if (matchHotkey(e, hotkeys.chapterExportJson)) {
    e.preventDefault()
    ctx.onChapterExportJson?.()
    return true
  }
  if (matchHotkey(e, hotkeys.chapterImportJson)) {
    e.preventDefault()
    ctx.onChapterImportJson?.()
    return true
  }

  // 8. Размер кисти (Стрелки вверх/вниз)
  if (matchHotkey(e, hotkeys.brushSizeUp)) {
    if (ctx.onBrushResize) {
      e.preventDefault()
      ctx.onBrushResize(+4)
      return true
    }
  }
  if (matchHotkey(e, hotkeys.brushSizeDown)) {
    if (ctx.onBrushResize) {
      e.preventDefault()
      ctx.onBrushResize(-4)
      return true
    }
  }

  // Все следующие хоткеи требуют выделенного бабла
  if (!selectedId) return false
  const activeBlock = textBlocks.find((b) => b.id === selectedId)
  if (!activeBlock) return false

  // 9. Одиночный OCR выбранного бабла [O]
  if (matchHotkey(e, hotkeys.ocrBlock)) {
    if (!ctx.onOcrBlock) return false
    e.preventDefault()
    ctx.onOcrBlock(activeBlock)
    return true
  }

  // 10. Смена типа бабла
  if (matchHotkey(e, hotkeys.setClassBubble)) {
    e.preventDefault()
    ctx.onSetClass?.(0) // Бабл
    return true
  }
  if (matchHotkey(e, hotkeys.setClassThought)) {
    e.preventDefault()
    ctx.onSetClass?.(1) // Мысли
    return true
  }
  if (matchHotkey(e, hotkeys.setClassText)) {
    e.preventDefault()
    ctx.onSetClass?.(2) // Текст
    return true
  }
  if (matchHotkey(e, hotkeys.setClassSfx)) {
    e.preventDefault()
    ctx.onSetClass?.(3) // SFX (Звук по F4)
    return true
  }

  // 11. Выбор шрифтов 1..7
  for (const font of MANGA_FONTS) {
    const actionKey = `font${font.index}` as HotkeyActionId
    const binding = hotkeys[actionKey]
    if (binding && matchHotkey(e, binding)) {
      e.preventDefault()
      ctx.onUpdateBlock(selectedId, { fontFamily: font.id })
      return true
    }
  }

  // 12. Точечный клин
  if (matchHotkey(e, hotkeys.spotWhiteDel)) {
    e.preventDefault()
    ctx.onSpotClean?.(activeBlock, "white", true)
    return true
  }
  if (matchHotkey(e, hotkeys.spotWhite)) {
    e.preventDefault()
    ctx.onSpotClean?.(activeBlock, "white", false)
    return true
  }
  if (matchHotkey(e, hotkeys.spotLamaDel)) {
    e.preventDefault()
    ctx.onSpotClean?.(activeBlock, "lama", true)
    return true
  }
  if (matchHotkey(e, hotkeys.spotLama)) {
    e.preventDefault()
    ctx.onSpotClean?.(activeBlock, "lama", false)
    return true
  }

  // 13. Удаление бабла (точечно поддерживаем Backspace, если на удаление назначен Delete)
  const backspaceDeletesBlock =
    hotkeys.deleteBlock.code === "Delete" &&
    e.code === "Backspace" &&
    !isCtrlOrMeta &&
    !e.shiftKey &&
    !e.altKey
  if (backspaceDeletesBlock || matchHotkey(e, hotkeys.deleteBlock)) {
    e.preventDefault()
    ctx.onDeleteBlock(selectedId)
    return true
  }

  // 14. Порядок чтения
  if (matchHotkey(e, hotkeys.moveOrderUp)) {
    e.preventDefault()
    ctx.onMoveBlock(selectedId, "up")
    return true
  }
  if (matchHotkey(e, hotkeys.moveOrderDown)) {
    e.preventDefault()
    ctx.onMoveBlock(selectedId, "down")
    return true
  }

  // 15. Размер шрифта
  const currentEffectiveFont = activeBlock.fontSize ?? defaultFontSize
  if (matchHotkey(e, hotkeys.fontSizeDown)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { fontSize: Math.max(8, currentEffectiveFont - 1) })
    return true
  }
  if (matchHotkey(e, hotkeys.fontSizeUp)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { fontSize: Math.min(48, currentEffectiveFont + 1) })
    return true
  }

  // 16. Геометрия и стили
  if (matchHotkey(e, hotkeys.toggleShape)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { shape: activeBlock.shape === "ellipse" ? "rect" : "ellipse" })
    return true
  }
  if (matchHotkey(e, hotkeys.toggleStroke)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { hasStroke: !activeBlock.hasStroke })
    return true
  }
  if (matchHotkey(e, hotkeys.togglePadding)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { paddingMode: activeBlock.paddingMode === "fit" ? "safe" : "fit" })
    return true
  }
  if (matchHotkey(e, hotkeys.toggleHyphenation)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { minHyphens: !(activeBlock.minHyphens !== false) })
    return true
  }
  if (matchHotkey(e, hotkeys.toggleBold)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { isBold: !activeBlock.isBold })
    return true
  }
  if (matchHotkey(e, hotkeys.toggleItalic)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { isItalic: !activeBlock.isItalic })
    return true
  }
  if (matchHotkey(e, hotkeys.toggleUppercase)) {
    e.preventDefault()
    ctx.onUpdateBlock(selectedId, { isUppercase: !activeBlock.isUppercase })
    return true
  }

  return false
}

// manga_ui/components/image-viewer/use-bubble-inline-editor.ts
// Логика инлайн-редактора: локальный текст, синхронизация с внешним Undo/Redo,
// переносы строк, авто-овал пустого бабла и commit/cancel по клавишам

"use client"

import type React from "react"
import { useEffect, useRef, useState } from "react"
import type { TextBlock } from "@/lib/types"
import {
  reflowFromManualLines,
  hasManualLineBreaks,
  hasModifiedLineBreaks,
  stripForcedSingleLineMarker,
  FORCED_SINGLE_LINE_MARKER,
} from "@/lib/typeset"
import type { ReflowOptions } from "@/lib/typeset"
import type { BubbleReflowedState } from "./use-bubble-screen-layout"

export interface UseBubbleInlineEditorParams {
  box: TextBlock
  editableLines: string[]
  finalScreenLineHeight: number
  masterBoxPixelH: number
  screenScale: number
  /** Автоматически превращать пустой бабл речи в овал после ввода перевода. */
  autoOvalBubble?: boolean
  computeReflowedState: (
    snapshotLines: string[],
    rawInput: string,
    options?: ReflowOptions
  ) => BubbleReflowedState
  onUpdate?: (id: string, patch: Partial<TextBlock>) => void
  /** Транзиентное обновление без нового шага Undo (для отката по Escape). */
  onUpdateTransient?: (id: string, patch: Partial<TextBlock>) => void
  /** Глубина стека Undo и её обрезка для отмены правки без «мусорных» шагов. */
  getHistoryDepth?: () => number
  onTruncateHistory?: (depth: number) => void
  onClose: () => void
}

export function useBubbleInlineEditor({
  box,
  editableLines,
  finalScreenLineHeight,
  masterBoxPixelH,
  screenScale,
  autoOvalBubble = true,
  computeReflowedState,
  onUpdate,
  onUpdateTransient,
  getHistoryDepth,
  onTruncateHistory,
  onClose,
}: UseBubbleInlineEditorParams) {
  const [localText, setLocalText] = useState(() =>
    editableLines.length > 0
      ? editableLines.join("\n")
      : stripForcedSingleLineMarker(box.rusText)
  )
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const snapshotLinesOnOpenRef = useRef<string[]>([...editableLines])
  const editableLinesRef = useRef<string[]>(editableLines)
  const lastEmittedStorageRef = useRef<string | null>(null)
  const originalStorageRef = useRef<string>(box.rusText || "")
  const originalShapeRef = useRef<TextBlock["shape"]>(box.shape)
  const historyDepthAtOpenRef = useRef<number>(getHistoryDepth?.() ?? 0)
  const isCancellingRef = useRef(false)
  const hasCommittedRef = useRef(false)
  // Был ли блок ручным до правки и менял ли пользователь разбивку строк.
  const wasManualBeforeEditRef = useRef(hasManualLineBreaks(box.rusText))
  const hadForcedSingleLineRef = useRef(Boolean(box.rusText?.includes(FORCED_SINGLE_LINE_MARKER)))
  const userTouchedBreaksRef = useRef(false)
  // Число строк на предыдущем onChange и факт Enter/Backspace по переносам.
  const prevLineCountRef = useRef(editableLines.length)
  const hadBreakEditRef = useRef(false)
  // Был ли русский текст пустым при открытии редактора: только в этом случае
  // авто-режим превращает бабл речи в овал после ввода перевода.
  const wasEmptyBeforeEditRef = useRef(!box.rusText?.trim())
  editableLinesRef.current = editableLines

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.focus()
    const len = ta.value.length
    ta.setSelectionRange(len, len)
  }, [])

  // Синхронизация при внешнем изменении текста бабла (например, после Undo / Ctrl+Z)
  useEffect(() => {
    // Не перетираем то, что пользователь только что набрал самим же onChange.
    if (box.rusText === lastEmittedStorageRef.current) return
    const lines = editableLinesRef.current
    setLocalText(
      lines.length > 0 ? lines.join("\n") : stripForcedSingleLineMarker(box.rusText)
    )
    snapshotLinesOnOpenRef.current = [...lines]
    wasManualBeforeEditRef.current = hasManualLineBreaks(box.rusText)
    hadForcedSingleLineRef.current = Boolean(box.rusText?.includes(FORCED_SINGLE_LINE_MARKER))
    userTouchedBreaksRef.current = false
    hadBreakEditRef.current = false
    prevLineCountRef.current = lines.length
  }, [box.rusText])

  const reflowOptions = (): ReflowOptions => ({
    wasManualBeforeEdit: wasManualBeforeEditRef.current,
    hasUserModifiedLineBreaks: userTouchedBreaksRef.current,
    hadForcedSingleLine: hadForcedSingleLineRef.current,
  })

  // Пустой бабл речи при вводе первого перевода становится овалом (если включена настройка).
  const shouldAutoOval = (storageText: string) =>
    (box.class_id ?? 0) === 0 &&
    autoOvalBubble &&
    wasEmptyBeforeEditRef.current &&
    box.shape === "rect" &&
    storageText.trim().length > 0

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const nextText = e.target.value
    setLocalText(nextText)

    // Вычисляем на каждом изменении, а не «залипаем» в true после первого Enter:
    // Backspace должен возвращать блок в авто-режим. Сравниваем распределение
    // слов по строкам — перенос слова между строками тоже ручная разбивка.
    const nextLineCount = nextText.split(/\r?\n/).length
    userTouchedBreaksRef.current = hasModifiedLineBreaks(
      snapshotLinesOnOpenRef.current,
      nextText,
      prevLineCountRef.current,
      hadBreakEditRef.current
    )
    if (nextLineCount !== prevLineCountRef.current) hadBreakEditRef.current = true
    prevLineCountRef.current = nextLineCount

    if (!onUpdate) return

    const storageText = reflowFromManualLines(
      snapshotLinesOnOpenRef.current,
      nextText,
      reflowOptions()
    )
    lastEmittedStorageRef.current = storageText

    const hasText = storageText.length > 0
    const patch: Partial<TextBlock> = {
      rusText: storageText,
      status: hasText ? "translated" : box.japText ? "ocr-done" : "new",
    }
    if (shouldAutoOval(storageText)) {
      patch.shape = "ellipse"
      wasEmptyBeforeEditRef.current = false
    }
    onUpdate(box.id, patch)
  }

  const commitInlineEdit = () => {
    if (isCancellingRef.current || hasCommittedRef.current) return
    hasCommittedRef.current = true
    onClose()
    const trimmed = localText.trim()

    if (trimmed === snapshotLinesOnOpenRef.current.join("\n").trim()) {
      return
    }

    const { storageText } = computeReflowedState(
      snapshotLinesOnOpenRef.current,
      trimmed,
      reflowOptions()
    )

    if (onUpdate) {
      const needsShape = shouldAutoOval(storageText)
      if (storageText === lastEmittedStorageRef.current && !needsShape) {
        return
      }
      const hasText = storageText.length > 0
      const patch: Partial<TextBlock> = {
        rusText: storageText,
        status: hasText ? "translated" : box.japText ? "ocr-done" : "new",
      }
      if (needsShape) {
        patch.shape = "ellipse"
        wasEmptyBeforeEditRef.current = false
      }
      onUpdate(box.id, patch)
    }
  }

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    e.stopPropagation()

    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      commitInlineEdit()
      return
    }

    if (e.key === "Escape") {
      e.preventDefault()
      isCancellingRef.current = true
      setLocalText(
        editableLines.length > 0
          ? editableLines.join("\n")
          : stripForcedSingleLineMarker(box.rusText)
      )

      // Откатываем текст и форму (авто-овал) без создания нового шага Undo,
      // затем убираем снапшоты, созданные во время этой правки.
      const applyPatch = onUpdateTransient ?? onUpdate
      if (applyPatch) {
        const patch: Partial<TextBlock> = {
          rusText: originalStorageRef.current,
          shape: originalShapeRef.current,
          status: originalStorageRef.current.trim()
            ? "translated"
            : box.japText
              ? "ocr-done"
              : "new",
        }
        applyPatch(box.id, patch)
      }
      onTruncateHistory?.(historyDepthAtOpenRef.current)
      onClose()
      return
    }
  }

  const editLinesCount = Math.max(2, localText.split("\n").length)
  const dynamicEditH = Math.max(
    masterBoxPixelH * screenScale,
    editLinesCount * (finalScreenLineHeight + 2) + 12
  )

  return {
    localText,
    textareaRef,
    dynamicEditH,
    handleTextareaChange,
    handleTextareaKeyDown,
    commitInlineEdit,
  }
}

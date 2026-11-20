// manga_ui/components/text-block-card/use-card-rus-editor.ts
// Расчёт видимых строк русского перевода, Enter с ручным переносом и сброс этих переносов

"use client"

import { useState, useRef, useEffect, useMemo } from "react"
import type { TextBlock } from "@/lib/types"
import {
  computeBubbleDisplayLines,
  reflowFromManualLines,
  joinLinesRemovingSoftHyphens,
  hasManualLineBreaks,
  hasModifiedLineBreaks,
  stripForcedSingleLineMarker,
  usePageImageMetrics,
  useFontsEpoch,
  FORCED_SINGLE_LINE_MARKER,
} from "@/lib/typeset"

export interface UseCardRusEditorProps {
  block: TextBlock
  defaultFontSize?: number
  autoOvalBubble?: boolean
  onChange: (patch: Partial<TextBlock>) => void
}

export interface UseCardRusEditorReturn {
  renderedLines: string[]
  localRusText: string
  setLocalRusText: React.Dispatch<React.SetStateAction<string>>
  rusTextareaRef: React.RefObject<HTMLTextAreaElement | null>
  isFocusedRus: boolean
  setIsFocusedRus: React.Dispatch<React.SetStateAction<boolean>>
  snapshotLinesRef: React.RefObject<string[]>
  saveStorageTextToBlock: (storageText: string) => void
  beginRusEditSession: () => void
  buildRusStorageText: (value: string) => string
  handleRusKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  handleRusTextChange: (value: string) => void
  handleClearManualBreaks: (e: React.MouseEvent) => void
  hasManualNewlines: boolean
  rusRows: number
}

export function useCardRusEditor({
  block,
  defaultFontSize = 14,
  autoOvalBubble = true,
  onChange,
}: UseCardRusEditorProps): UseCardRusEditorReturn {
  const [isFocusedRus, setIsFocusedRus] = useState(false)
  const [localRusText, setLocalRusText] = useState(() => stripForcedSingleLineMarker(block.rusText))
  // Эпоха загрузки шрифтов: меняется при догрузке манга-шрифта, кэши вёрстки
  // при этом очищаются, а renderedLines пересчитывается.
  const fontsEpoch = useFontsEpoch()

  const { naturalW, naturalH } = usePageImageMetrics()

  const rusTextareaRef = useRef<HTMLTextAreaElement>(null)
  const snapshotLinesRef = useRef<string[]>([])
  // Последний реально отправленный в блок storage-текст — защищает от
  // повторного сохранения того же текста при onBlur (холостой шаг Undo).
  const lastEmittedStorageRef = useRef<string>(block.rusText || "")
  // Был ли блок ручным до начала правки и менял ли пользователь разбивку строк.
  const wasManualBeforeEditRef = useRef(false)
  const hadForcedSingleLineRef = useRef(false)
  const userTouchedBreaksRef = useRef(false)
  // Число строк на предыдущем onChange и факт Enter/Backspace по переносам:
  // позволяет отличить перенос слова между строками от простой правки текста.
  const prevLineCountRef = useRef(0)
  const hadBreakEditRef = useRef(false)

  // Внешнее изменение текста (Undo / Redo / смена блока) сбрасывает защиту
  // и ручную правку переносов; собственные onchange-эмиссии не трогаем.
  useEffect(() => {
    const next = block.rusText || ""
    if (next !== lastEmittedStorageRef.current) {
      userTouchedBreaksRef.current = false
      hadBreakEditRef.current = false
      prevLineCountRef.current = 0
    }
    lastEmittedStorageRef.current = next
  }, [block.rusText])

  const renderedLines = useMemo(() => {
    if (typeof document === "undefined") return (block.rusText || "").split(/\r?\n/)
    if (!(block.rusText || "").trim()) return []

    const display = computeBubbleDisplayLines(
      block,
      { naturalW, naturalH },
      defaultFontSize,
      block.width,
      block.height
    )

    // Маркер однострочности НЕ добавляем: в textarea должен быть только
    // чистый видимый текст, иначе Backspace удаляет невидимый \u2060.
    return [...display.editableLines]
  }, [
    block.rusText,
    block.width,
    block.height,
    block.fontSize,
    block.fontFamily,
    block.shape,
    block.paddingMode,
    block.isBold,
    block.isItalic,
    block.isUppercase,
    block.minHyphens,
    defaultFontSize,
    naturalW,
    naturalH,
    fontsEpoch,
  ])

  useEffect(() => {
    if (!isFocusedRus) {
      const displayStr =
        renderedLines.length > 0
          ? renderedLines.join("\n")
          : stripForcedSingleLineMarker(block.rusText)
      setLocalRusText(displayStr)
      snapshotLinesRef.current = [...renderedLines]
      prevLineCountRef.current = renderedLines.length
      hadBreakEditRef.current = false
    }
  }, [renderedLines, block.rusText, isFocusedRus])

  const currentClassId = block.class_id ?? 0

  const saveStorageTextToBlock = (storageText: string) => {
    const hasText = storageText.trim().length > 0
    const patch: Partial<TextBlock> = {
      rusText: storageText,
      status: hasText ? "translated" : block.japText ? "ocr-done" : "new",
    }
    if (currentClassId === 0 && autoOvalBubble && !block.shape) {
      patch.shape = hasText ? "ellipse" : "rect"
    } else if (
      currentClassId === 0 &&
      autoOvalBubble &&
      hasText &&
      block.shape === "rect" &&
      !block.rusText
    ) {
      patch.shape = "ellipse"
    }

    const storedText = block.rusText || ""
    const needsShapeChange = patch.shape !== undefined && patch.shape !== block.shape
    const needsStatusChange = patch.status !== block.status

    // Текст уже сохранён (например, при onBlur после живого ввода) и форма/статус
    // не меняются — не создаём дублирующий снапшот в истории Undo.
    if (storageText === storedText && !needsShapeChange && !needsStatusChange) {
      lastEmittedStorageRef.current = storageText
      return
    }

    lastEmittedStorageRef.current = storageText
    onChange(patch)
  }

  // Запоминаем состояние на момент фокуса: какие строки были на скане,
  // был ли блок ручным и был ли он принудительно однострочным.
  const beginRusEditSession = () => {
    snapshotLinesRef.current = [...renderedLines]
    wasManualBeforeEditRef.current = hasManualLineBreaks(block.rusText)
    hadForcedSingleLineRef.current = Boolean(block.rusText?.includes(FORCED_SINGLE_LINE_MARKER))
    userTouchedBreaksRef.current = false
    hadBreakEditRef.current = false
    prevLineCountRef.current = snapshotLinesRef.current.length
  }

  /**
   * Собирает storage-текст из значения textarea. Если пользователь только
   * исправил символ (число строк не изменилось и Enter/Backspace не трогали
   * переносы), блок остаётся в авто-режиме.
   */
  const buildRusStorageText = (value: string) => {
    const editedLineCount = value.split(/\r?\n/).length
    // Сравниваем распределение слов по строкам, а не только их количество:
    // иначе перенос слова между строками при том же числе строк терялся.
    userTouchedBreaksRef.current = hasModifiedLineBreaks(
      snapshotLinesRef.current,
      value,
      prevLineCountRef.current,
      hadBreakEditRef.current
    )
    if (editedLineCount !== prevLineCountRef.current) hadBreakEditRef.current = true
    prevLineCountRef.current = editedLineCount

    return reflowFromManualLines(snapshotLinesRef.current, value, {
      wasManualBeforeEdit: wasManualBeforeEditRef.current,
      hasUserModifiedLineBreaks: userTouchedBreaksRef.current,
      hadForcedSingleLine: hadForcedSingleLineRef.current,
    })
  }

  // Enter, Backspace и Delete должны работать нативно, как в обычном блокноте.
  // Никакого preventDefault и пересчёта текста здесь быть не должно.
  const handleRusKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    e.stopPropagation()
  }

  // Живое сохранение: пользователь ставит перенос — скан сразу перерисовывается,
  // но содержимое textarea не перезаписывается результатом авто-вёрстки.
  const handleRusTextChange = (value: string) => {
    setLocalRusText(value)
    saveStorageTextToBlock(buildRusStorageText(value))
  }

  const handleClearManualBreaks = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!block.rusText) return
    const rawLines = block.rusText
      .replace(/\u2060/g, "")
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)

    const cleaned = joinLinesRemovingSoftHyphens(rawLines)
    saveStorageTextToBlock(cleaned)
  }

  const hasManualNewlines = hasManualLineBreaks(block.rusText)
  const rusRows = Math.min(6, Math.max(1, localRusText.split(/\r?\n/).length))

  return {
    renderedLines,
    localRusText,
    setLocalRusText,
    rusTextareaRef,
    isFocusedRus,
    setIsFocusedRus,
    snapshotLinesRef,
    saveStorageTextToBlock,
    beginRusEditSession,
    buildRusStorageText,
    handleRusKeyDown,
    handleRusTextChange,
    handleClearManualBreaks,
    hasManualNewlines,
    rusRows,
  }
}

// manga_ui/components/image-viewer/bubble-inline-editor.tsx
// Инлайн-редактор текста прямо на скане: Enter — нативный перенос, Ctrl+Enter — готово, Esc — отмена
// Логика состояния и commit/cancel вынесена в use-bubble-inline-editor.ts

"use client"

import type React from "react"
import type { TextBlock } from "@/lib/types"
import type { ReflowOptions } from "@/lib/typeset"
import type { BubbleReflowedState } from "./use-bubble-screen-layout"
import { useBubbleInlineEditor } from "./use-bubble-inline-editor"

export interface BubbleInlineEditorProps {
  box: TextBlock
  editableLines: string[]
  currentX: number
  currentY: number
  currentW: number
  currentH: number
  currentRot: number
  currentFont: string
  isWhiteText: boolean
  finalScreenFontSize: number
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
  onUpdateTransient?: (id: string, patch: Partial<TextBlock>) => void
  getHistoryDepth?: () => number
  onTruncateHistory?: (depth: number) => void
  onClose: () => void
}

export function BubbleInlineEditor({
  box,
  editableLines,
  currentX,
  currentY,
  currentW,
  currentH,
  currentRot,
  currentFont,
  isWhiteText,
  finalScreenFontSize,
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
}: BubbleInlineEditorProps) {
  const editor = useBubbleInlineEditor({
    box,
    editableLines,
    finalScreenLineHeight,
    masterBoxPixelH,
    screenScale,
    autoOvalBubble,
    computeReflowedState,
    onUpdate,
    onUpdateTransient,
    getHistoryDepth,
    onTruncateHistory,
    onClose,
  })

  return (
    <div
      id={`box-${box.id}`}
      className="absolute z-50 flex items-center justify-center"
      style={{
        left: `${currentX * 100}%`,
        top: `${currentY * 100}%`,
        width: `${currentW * 100}%`,
        height: `${currentH * 100}%`,
        transform: `rotate(${currentRot}deg)`,
        transformOrigin: "center center",
      }}
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div
        className="relative flex items-center justify-center w-full min-w-[120px]"
        style={{ height: `${editor.dynamicEditH}px` }}
      >
        <textarea
          ref={editor.textareaRef}
          value={editor.localText}
          onChange={editor.handleTextareaChange}
          onKeyDown={editor.handleTextareaKeyDown}
          onBlur={editor.commitInlineEdit}
          wrap="off"
          placeholder="Текст..."
          className={[
            "w-full h-full p-1.5 text-center outline-none border-2 border-indigo-500 rounded-md shadow-2xl backdrop-blur-md overflow-x-auto overflow-y-auto resize-none",
            isWhiteText
              ? "bg-slate-900/95 text-white placeholder:text-slate-400"
              : "bg-white/95 text-black placeholder:text-slate-500",
            box.isBold ? "font-bold" : "font-normal",
            box.isItalic ? "italic" : "not-italic",
            box.isUppercase ? "uppercase" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          style={{
            fontFamily: `'${currentFont}', sans-serif`,
            fontSize: `${Math.max(11, finalScreenFontSize)}px`,
            lineHeight: `${Math.max(13, finalScreenLineHeight)}px`,
          }}
        />
      </div>
      <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-slate-950 px-1.5 py-0.5 text-[9px] text-slate-300 border border-slate-700 pointer-events-none shadow">
        Enter: перенос строки | Ctrl+Enter: готово | Esc: отмена
      </div>
    </div>
  )
}

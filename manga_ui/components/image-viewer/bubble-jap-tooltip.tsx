// manga_ui/components/image-viewer/bubble-jap-tooltip.tsx
// Интерактивная плашка японского оригинала на скане:
// - без мешающего браузерного title
// - свободное перетаскивание (Drag) за шапку с сохранением смещения japOffset
// - прямое редактирование японского текста (по кнопке карандаша или двойному клику по тексту)
// - встроенный морфологический разбор и локальный словарь (Warodai + JMdict + Глоссарий тайтла)
// Вся логика состояния и расчётов вынесена в use-jap-tooltip-controller.ts

"use client"

import React from "react"
import { GripHorizontal, Pencil, Check, X, RotateCcw } from "lucide-react"
import type { TextBlock } from "@/lib/types"
import { TokenizedBubbleText } from "./tokenized-bubble-text"
import type { JapPlatePlacement } from "./jap-overlay-placement"
import { useJapTooltipController } from "./use-jap-tooltip-controller"

export interface BubbleJapTooltipProps {
  box: TextBlock
  index: number
  titleId?: number | null
  isSelected: boolean
  showJapOverlay: boolean
  isDraft: boolean
  isInlineEditing: boolean
  currentX: number
  currentY: number
  currentW: number
  currentH: number
  /** Свободная позиция плашки, посчитанная централизованно (нормализованные координаты страницы). */
  autoJapPlacement?: JapPlatePlacement | null
  onSelect: (id: string) => void
  onUpdate?: (id: string, patch: Partial<TextBlock>) => void
  onUpdateTransient?: (id: string, patch: Partial<TextBlock>) => void
}

export function BubbleJapTooltip({
  box,
  index,
  titleId,
  isSelected,
  showJapOverlay,
  isDraft,
  isInlineEditing,
  currentX,
  currentY,
  currentW,
  currentH,
  autoJapPlacement = null,
  onSelect,
  onUpdate,
  onUpdateTransient,
}: BubbleJapTooltipProps) {
  const ctrl = useJapTooltipController({
    box,
    titleId,
    showJapOverlay,
    isDraft,
    isInlineEditing,
    currentX,
    currentY,
    currentW,
    currentH,
    autoJapPlacement,
    onSelect,
    onUpdate,
    onUpdateTransient,
  })

  if (!ctrl.isVisible) return null

  return (
    <div
      lang="ja"
      onMouseDown={(e) => {
        e.stopPropagation()
        onSelect(box.id)
      }}
      onClick={(e) => {
        e.stopPropagation()
        onSelect(box.id)
      }}
      onDoubleClick={(e) => {
        e.stopPropagation()
      }}
      className={[
        "absolute min-w-[160px] max-w-[280px] rounded-lg px-2.5 py-1.5",
        "bg-slate-950/95 text-slate-100 shadow-xl backdrop-blur-md",
        "pointer-events-auto whitespace-pre-wrap break-words",
        ctrl.isDragging || ctrl.isEditingJap ? "z-50" : "z-40",
        isSelected
          ? "border-2 border-amber-400/90 ring-2 ring-amber-400/25"
          : "border border-indigo-500/60 hover:border-indigo-400",
      ].join(" ")}
      style={{
        ...ctrl.autoPositionStyle,
        fontSize: "17px",
        lineHeight: 1.4,
        fontFamily: "'Hiragino Kaku Gothic ProN', 'Yu Gothic', 'Meiryo', 'Noto Sans JP', sans-serif",
        fontWeight: 500,
        fontStyle: "normal",
        textShadow: "none",
        transform: ctrl.combinedTransform,
      }}
    >
      {/* Шапка плашки — зона перетаскивания (Drag Handle) и быстрых кнопок */}
      <div
        onMouseDown={ctrl.handleHeaderMouseDown}
        onDoubleClick={ctrl.handleResetOffset}
        className={[
          "mb-1 flex items-center justify-between gap-1.5 border-b border-slate-800/80 pb-1 text-[10px] font-sans font-bold text-indigo-300 select-none",
          ctrl.isDragging ? "cursor-grabbing" : "cursor-grab",
        ].join(" ")}
      >
        <div className="flex items-center gap-1 min-w-0">
          <GripHorizontal className="h-3 w-3 shrink-0 text-slate-500" />
          <span className="shrink-0">#{index + 1} JP</span>
          {box.speaker && (
            <span className="truncate text-emerald-400 font-medium ml-1">{box.speaker}</span>
          )}
        </div>

        <div
          className="flex items-center gap-0.5 shrink-0"
          onMouseDown={(e) => e.stopPropagation()}
        >
          {ctrl.hasCustomOffset && (
            <button
              type="button"
              onClick={ctrl.handleResetOffset}
              className="rounded p-0.5 text-slate-400 hover:bg-slate-800 hover:text-amber-300 transition-colors"
              aria-label="Сбросить позицию"
            >
              <RotateCcw className="h-2.5 w-2.5" />
            </button>
          )}

          {!ctrl.isEditingJap ? (
            <button
              type="button"
              onClick={ctrl.startEditingJap}
              className="rounded p-0.5 text-slate-400 hover:bg-slate-800 hover:text-indigo-300 transition-colors"
              aria-label="Редактировать японский текст"
            >
              <Pencil className="h-2.5 w-2.5" />
            </button>
          ) : (
            <>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  ctrl.commitJapEdit()
                }}
                className="rounded p-0.5 text-emerald-400 hover:bg-emerald-950/80 hover:text-emerald-200 transition-colors"
                aria-label="Сохранить"
              >
                <Check className="h-3 w-3" />
              </button>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  ctrl.cancelJapEdit(e)
                }}
                className="rounded p-0.5 text-rose-400 hover:bg-rose-950/80 hover:text-rose-200 transition-colors"
                aria-label="Отменить"
              >
                <X className="h-3 w-3" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Тело плашки: интерактивный токенизированный текст со словарём ИЛИ режим редактирования */}
      {!ctrl.isEditingJap ? (
        <TokenizedBubbleText
          japText={box.japText || ""}
          tokens={ctrl.tokens}
          titleId={titleId}
          onStartEdit={ctrl.startEditingJap}
          onSetSpeaker={(speakerName) => onUpdate?.(box.id, { speaker: speakerName })}
        />
      ) : (
        <div className="space-y-1">
          <textarea
            ref={ctrl.textareaRef}
            value={ctrl.draftJap}
            rows={ctrl.editRows}
            onChange={(e) => ctrl.setDraftJap(e.target.value)}
            onKeyDown={ctrl.handleTextareaKeyDown}
            onBlur={ctrl.commitJapEdit}
            className="w-full min-w-[180px] resize-y rounded border border-indigo-500/80 bg-slate-900 px-1.5 py-1 text-[16px] leading-snug text-white outline-none focus:ring-1 focus:ring-indigo-400"
            style={{
              fontFamily: "'Hiragino Kaku Gothic ProN', 'Yu Gothic', 'Meiryo', 'Noto Sans JP', sans-serif",
            }}
          />
          <div className="text-[9px] font-sans text-slate-400 select-none flex justify-between">
            <span>Enter — сохр.</span>
            <span>Shift+Enter — строка</span>
            <span>Esc — отмена</span>
          </div>
        </div>
      )}
    </div>
  )
}

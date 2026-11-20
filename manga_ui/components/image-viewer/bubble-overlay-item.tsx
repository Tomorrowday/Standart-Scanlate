"use client"

// manga_ui/components/image-viewer/bubble-overlay-item.tsx
/**
 * Контракт наложения интерактивного бабла на скан (трансформация, инлайн-редактирование, тайпсет, плашка японского оригинала).
 * Состав реализации: bubble-constants.ts, use-bubble-screen-layout.ts, bubble-inline-editor.tsx,
 *                    bubble-resize-handles.tsx, bubble-jap-tooltip.tsx,
 *                    bubble-typeset-view.tsx, bubble-color-frame-view.tsx
 */

import type { TextBlock } from "@/lib/types"
import type { DrawRect } from "@/hooks/use-box-transform"
import type { JapPlatePlacement } from "./jap-overlay-placement"
import React, { memo, useState } from "react"
import type { EditAction } from "@/hooks/use-box-transform"
import { useBubbleScreenLayout } from "./use-bubble-screen-layout"
import { BubbleInlineEditor } from "./bubble-inline-editor"
import { BubbleJapTooltip } from "./bubble-jap-tooltip"
import { BubbleResizeHandles } from "./bubble-resize-handles"
import { BubbleTypesetView } from "./bubble-typeset-view"
import { BubbleColorFrameView } from "./bubble-color-frame-view"

export interface BubbleOverlayItemProps {
  box: TextBlock
  index: number
  titleId?: number | null
  isSelected: boolean
  showTypeset: boolean
  showJapOverlay?: boolean
  /** Вычисленная централизованно свободная позиция плашки JP (нормализованные координаты страницы). */
  autoJapPlacement?: JapPlatePlacement | null
  imgElement: HTMLImageElement | null
  isEditingCurrent: boolean
  editType: EditAction | null
  activeBox: DrawRect | null
  activeRotation: number
  defaultFontSize?: number
  /** Автоматически превращать пустой бабл речи в овал после ввода перевода. */
  autoOvalBubble?: boolean
  onStartTransform: (e: React.MouseEvent, box: TextBlock, action: EditAction) => void
  onSelect: (id: string) => void
  onUpdate?: (id: string, patch: Partial<TextBlock>) => void
  onUpdateTransient?: (id: string, patch: Partial<TextBlock>) => void
  getHistoryDepth?: () => number
  onTruncateHistory?: (depth: number) => void
}

export const BubbleOverlayItem = memo(function BubbleOverlayItem({
  box,
  index,
  titleId,
  isSelected,
  showTypeset,
  showJapOverlay = false,
  autoJapPlacement = null,
  imgElement,
  isEditingCurrent,
  editType,
  activeBox,
  activeRotation,
  defaultFontSize = 14,
  autoOvalBubble = true,
  onStartTransform,
  onSelect,
  onUpdate,
  onUpdateTransient,
  getHistoryDepth,
  onTruncateHistory,
}: BubbleOverlayItemProps) {
  const isDraft = box.id === "__draft__"
  const hasTranslation = Boolean(box.rusText && box.rusText.trim())
  const isEllipse = box.shape === "ellipse"
  const isWhiteText = box.textColor === "white"

  const [isInlineEditing, setIsInlineEditing] = useState(false)

  const currentX = isEditingCurrent && activeBox ? activeBox.x : box.x
  const currentY = isEditingCurrent && activeBox ? activeBox.y : box.y
  const currentW = isEditingCurrent && activeBox ? activeBox.width : box.width
  const currentH = isEditingCurrent && activeBox ? activeBox.height : box.height
  const currentRot = isEditingCurrent && editType === "rotate" ? activeRotation : box.rotation || 0

  const {
    screenLines,
    editableLines,
    finalScreenFontSize,
    finalScreenLineHeight,
    currentFont,
    masterBoxPixelH,
    screenScale,
    computeReflowedState,
  } = useBubbleScreenLayout({ imgElement, box, currentW, currentH, defaultFontSize })

  const handleMouseDown = (e: React.MouseEvent, action: EditAction) => {
    if (e.button !== 0) return
    if (isInlineEditing) return
    e.stopPropagation()
    onSelect(box.id)
    onStartTransform(e, box, action)
  }

  const handleDoubleClick = (e: React.MouseEvent) => {
    if (isDraft) return
    e.stopPropagation()
    onSelect(box.id)
    setIsInlineEditing(true)
  }

  const handlesNode = (
    <BubbleResizeHandles
      isSelected={isSelected}
      isInlineEditing={isInlineEditing}
      currentRot={currentRot}
      isEditingCurrent={isEditingCurrent}
      editType={editType}
      onStartAction={handleMouseDown}
    />
  )

  const japTooltipNode = (
    <BubbleJapTooltip
      box={box}
      index={index}
      titleId={titleId}
      isSelected={isSelected}
      showJapOverlay={showJapOverlay}
      autoJapPlacement={autoJapPlacement}
      isDraft={isDraft}
      isInlineEditing={isInlineEditing}
      currentX={currentX}
      currentY={currentY}
      currentW={currentW}
      currentH={currentH}
      onSelect={onSelect}
      onUpdate={onUpdate}
      onUpdateTransient={onUpdateTransient}
    />
  )

  const positionProps = {
    currentX,
    currentY,
    currentW,
    currentH,
    currentRot,
    onMouseDown: handleMouseDown,
    onDoubleClick: handleDoubleClick,
    handles: handlesNode,
  }

  if (isInlineEditing) {
    return (
      <BubbleInlineEditor
        box={box}
        editableLines={editableLines}
        currentX={currentX}
        currentY={currentY}
        currentW={currentW}
        currentH={currentH}
        currentRot={currentRot}
        currentFont={currentFont}
        isWhiteText={isWhiteText}
        finalScreenFontSize={finalScreenFontSize}
        finalScreenLineHeight={finalScreenLineHeight}
        masterBoxPixelH={masterBoxPixelH}
        screenScale={screenScale}
        autoOvalBubble={autoOvalBubble}
        computeReflowedState={computeReflowedState}
        onUpdate={onUpdate}
        onUpdateTransient={onUpdateTransient}
        getHistoryDepth={getHistoryDepth}
        onTruncateHistory={onTruncateHistory}
        onClose={() => setIsInlineEditing(false)}
      />
    )
  }

  if (showTypeset && !isDraft && hasTranslation) {
    return (
      <>
        <BubbleTypesetView
          box={box}
          screenLines={screenLines}
          isEllipse={isEllipse}
          isWhiteText={isWhiteText}
          isSelected={isSelected}
          showJapOverlay={showJapOverlay}
          currentFont={currentFont}
          finalScreenFontSize={finalScreenFontSize}
          finalScreenLineHeight={finalScreenLineHeight}
          {...positionProps}
        />
        {/* Плашка JP рендерится рядом, а не внутри повёрнутого контейнера бабла:
            так её текст не растеризуется вместе с вращением и остаётся чётким. */}
        {japTooltipNode}
      </>
    )
  }

  return (
    <>
      <BubbleColorFrameView
        box={box}
        index={index}
        isDraft={isDraft}
        isEllipse={isEllipse}
        isSelected={isSelected}
        showJapOverlay={showJapOverlay}
        {...positionProps}
      />
      {japTooltipNode}
    </>
  )
})

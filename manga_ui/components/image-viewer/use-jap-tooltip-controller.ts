// manga_ui/components/image-viewer/use-jap-tooltip-controller.ts
// Контроллер плашки японского оригинала: загрузка токенов, подписка на обновление глоссария,
// перетаскивание за шапку (japOffset), редактирование japText и расчёт позиции/трансформа

"use client"

import React, { useCallback, useEffect, useRef, useState } from "react"
import type { TextBlock } from "@/lib/types"
import {
  analyzeBubbleJapText,
  DICT_GLOSSARY_UPDATED_EVENT,
  type TokenSpan,
} from "@/lib/api/dictionary"
import type { JapPlatePlacement } from "./jap-overlay-placement"

export interface UseJapTooltipControllerParams {
  box: TextBlock
  titleId?: number | null
  showJapOverlay: boolean
  isDraft: boolean
  isInlineEditing: boolean
  currentX: number
  currentY: number
  currentW: number
  currentH: number
  autoJapPlacement?: JapPlatePlacement | null
  onSelect: (id: string) => void
  onUpdate?: (id: string, patch: Partial<TextBlock>) => void
  /** Транзиентное обновление без Undo/грязного флага (для japOffset). */
  onUpdateTransient?: (id: string, patch: Partial<TextBlock>) => void
}

export function useJapTooltipController({
  box,
  titleId,
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
}: UseJapTooltipControllerParams) {
  const [isEditingJap, setIsEditingJap] = useState(false)
  const [draftJap, setDraftJap] = useState(box.japText || "")
  const [isDragging, setIsDragging] = useState(false)
  const [liveOffset, setLiveOffset] = useState<{ x: number; y: number } | null>(null)
  const [tokens, setTokens] = useState<TokenSpan[] | null>(null)
  const [glossaryTick, setGlossaryTick] = useState(0)

  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const dragSessionRef = useRef<{
    startMouseX: number
    startMouseY: number
    startOffsetX: number
    startOffsetY: number
  } | null>(null)

  // Синхронизируем локальный черновик при внешнем обновлении japText (OCR / Undo / Redo)
  useEffect(() => {
    if (!isEditingJap) {
      setDraftJap(box.japText || "")
    }
  }, [box.japText, isEditingJap])

  // Подписка на глобальное событие обновления глоссария тайтла
  useEffect(() => {
    const handleGlossaryUpdated = () => setGlossaryTick((t) => t + 1)
    window.addEventListener(DICT_GLOSSARY_UPDATED_EVENT, handleGlossaryUpdated)
    return () => window.removeEventListener(DICT_GLOSSARY_UPDATED_EVENT, handleGlossaryUpdated)
  }, [])

  // Запрос морфологического разбора и словарных статей при показе плашки JP
  useEffect(() => {
    const raw = (box.japText || "").trim()
    if (!showJapOverlay || isDraft || !raw) {
      setTokens(null)
      return
    }

    let cancelled = false
    analyzeBubbleJapText(raw, titleId)
      .then((res) => {
        if (!cancelled) setTokens(res)
      })
      .catch(() => {
        if (!cancelled) setTokens(null)
      })

    return () => {
      cancelled = true
    }
  }, [showJapOverlay, isDraft, box.japText, titleId, glossaryTick])

  // Автофокус и установка курсора в конец при открытии редактора
  useEffect(() => {
    if (isEditingJap && textareaRef.current) {
      const ta = textareaRef.current
      ta.focus()
      const len = ta.value.length
      ta.setSelectionRange(len, len)
    }
  }, [isEditingJap])

  const savedOffset = box.japOffset ?? { x: 0, y: 0 }
  const activeOffset = liveOffset ?? savedOffset
  const hasCustomOffset = Math.abs(activeOffset.x) > 1 || Math.abs(activeOffset.y) > 1

  // Обработка глобального перетаскивания плашки за шапку
  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent) => {
      const session = dragSessionRef.current
      if (!session) return

      const rawDx = e.clientX - session.startMouseX
      const rawDy = e.clientY - session.startMouseY

      setLiveOffset({
        x: Math.round(session.startOffsetX + rawDx),
        y: Math.round(session.startOffsetY + rawDy),
      })
    }

    const handleMouseUp = (e: MouseEvent) => {
      const session = dragSessionRef.current
      dragSessionRef.current = null
      setIsDragging(false)

      if (!session) return
      const finalX = Math.round(session.startOffsetX + (e.clientX - session.startMouseX))
      const finalY = Math.round(session.startOffsetY + (e.clientY - session.startMouseY))

      setLiveOffset(null)
      if (Math.abs(finalX - session.startOffsetX) > 1 || Math.abs(finalY - session.startOffsetY) > 1) {
        // japOffset намеренно не сохраняется в БД: без Undo-шага и без dirty-флага.
        ;(onUpdateTransient ?? onUpdate)?.(box.id, { japOffset: { x: finalX, y: finalY } })
      }
    }

    window.addEventListener("mousemove", handleMouseMove)
    window.addEventListener("mouseup", handleMouseUp)
    return () => {
      window.removeEventListener("mousemove", handleMouseMove)
      window.removeEventListener("mouseup", handleMouseUp)
    }
  }, [isDragging, box.id, onUpdate, onUpdateTransient])

  const handleHeaderMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return
    e.stopPropagation()
    e.preventDefault()
    onSelect(box.id)

    dragSessionRef.current = {
      startMouseX: e.clientX,
      startMouseY: e.clientY,
      startOffsetX: savedOffset.x,
      startOffsetY: savedOffset.y,
    }
    setLiveOffset(savedOffset)
    setIsDragging(true)
  }

  const handleResetOffset = (e: React.MouseEvent) => {
    e.stopPropagation()
    setLiveOffset(null)
    ;(onUpdateTransient ?? onUpdate)?.(box.id, { japOffset: { x: 0, y: 0 } })
  }

  const startEditingJap = (e?: React.MouseEvent) => {
    e?.stopPropagation()
    onSelect(box.id)
    setDraftJap(box.japText || "")
    setIsEditingJap(true)
  }

  const commitJapEdit = useCallback(() => {
    setIsEditingJap(false)
    const trimmed = draftJap.trim()
    const prevTrimmed = (box.japText || "").trim()
    if (trimmed === prevTrimmed) return

    const nextStatus =
      box.status === "translated" || Boolean(box.rusText && box.rusText.trim())
        ? "translated"
        : trimmed
          ? "ocr-done"
          : "new"

    onUpdate?.(box.id, {
      japText: trimmed,
      status: nextStatus,
    })
  }, [draftJap, box.id, box.japText, box.rusText, box.status, onUpdate])

  const cancelJapEdit = (e?: React.MouseEvent) => {
    e?.stopPropagation()
    setDraftJap(box.japText || "")
    setIsEditingJap(false)
  }

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    e.stopPropagation()

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      commitJapEdit()
      return
    }

    if (e.key === "Escape") {
      e.preventDefault()
      setDraftJap(box.japText || "")
      setIsEditingJap(false)
    }
  }

  const hasJapText = Boolean(box.japText && box.japText.trim())
  const isVisible =
    showJapOverlay && !isDraft && !isInlineEditing && (hasJapText || isEditingJap)

  // Позиция плашки задаётся в нормализованных координатах страницы (не внутри
  // повёрнутого контейнера бабла). Поэтому при вращении бабла плашка не уезжает
  // по дуге, а текст всегда остаётся ровным и чётким.
  const hasAutoPlacement =
    Boolean(autoJapPlacement) && currentW > 0.0001 && currentH > 0.0001

  let baseTranslate = ""
  let autoPositionStyle: React.CSSProperties

  if (hasAutoPlacement && autoJapPlacement) {
    autoPositionStyle = {
      left: `${autoJapPlacement.x * 100}%`,
      top: `${autoJapPlacement.y * 100}%`,
    }
  } else {
    // Резервный автоподбор базовой стороны вокруг бабла по свободному месту до краёв страницы
    const spaceRight = 1 - (currentX + currentW)
    const spaceLeft = currentX
    const spaceBottom = 1 - (currentY + currentH)

    if (spaceRight >= 0.22) {
      autoPositionStyle = {
        left: `${(currentX + currentW) * 100}%`,
        top: `${currentY * 100}%`,
      }
    } else if (spaceLeft >= 0.22) {
      autoPositionStyle = {
        right: `${(1 - currentX) * 100}%`,
        top: `${currentY * 100}%`,
      }
    } else if (spaceBottom >= 0.14) {
      autoPositionStyle = {
        left: `${(currentX + currentW / 2) * 100}%`,
        top: `${(currentY + currentH) * 100}%`,
      }
      baseTranslate = "translateX(-50%)"
    } else {
      autoPositionStyle = {
        left: `${(currentX + currentW / 2) * 100}%`,
        bottom: `${(1 - currentY) * 100}%`,
      }
      baseTranslate = "translateX(-50%)"
    }
  }

  // Только целочисленный сдвиг пользователя — никакого translate3d и вращения,
  // иначе Chromium теряет субпиксельное сглаживание японских иероглифов.
  const transformParts: string[] = []
  if (baseTranslate) transformParts.push(baseTranslate)
  const offsetX = Math.round(activeOffset.x)
  const offsetY = Math.round(activeOffset.y)
  if (offsetX !== 0 || offsetY !== 0) {
    transformParts.push(`translate(${offsetX}px, ${offsetY}px)`)
  }
  const combinedTransform = transformParts.length > 0 ? transformParts.join(" ") : undefined

  const editRows = Math.min(8, Math.max(2, draftJap.split(/\r?\n/).length))

  return {
    isVisible,
    tokens,
    isEditingJap,
    draftJap,
    setDraftJap,
    isDragging,
    textareaRef,
    hasCustomOffset,
    autoPositionStyle,
    combinedTransform,
    editRows,
    handleHeaderMouseDown,
    handleResetOffset,
    startEditingJap,
    commitJapEdit,
    cancelJapEdit,
    handleTextareaKeyDown,
  }
}

"use client"

// manga_ui/components/image-viewer/use-bubble-screen-layout.ts
// Экранная вёрстка текста бабла: метрики картинки, ожидание шрифтов,
// расчёт кегля, междустрочного интервала и reflow ручных переносов.
// Сам расчёт строк — в едином helper'е computeBubbleDisplayLines.

import type { TextBlock } from "@/lib/types"
import { useMemo } from "react"
import {
  computeBubbleDisplayLines,
  reflowFromManualLines,
  useFontsEpoch,
  usePageImageMetrics,
} from "@/lib/typeset"
import type { ReflowOptions } from "@/lib/typeset"

export interface BubbleReflowedState {
  storageText: string
}

export interface UseBubbleScreenLayoutParams {
  /** Оставлен для совместимости: метрики теперь читаются из общего стора. */
  imgElement?: HTMLImageElement | null
  box: TextBlock
  currentW: number
  currentH: number
  defaultFontSize: number
}

export interface BubbleScreenLayout {
  screenLines: string[]
  editableLines: string[]
  finalScreenFontSize: number
  finalScreenLineHeight: number
  currentFont: string
  masterBoxPixelH: number
  screenScale: number
  computeReflowedState: (
    snapshotLines: string[],
    rawInput: string,
    options?: ReflowOptions
  ) => BubbleReflowedState
}

export function useBubbleScreenLayout({
  box,
  currentW,
  currentH,
  defaultFontSize,
}: UseBubbleScreenLayoutParams): BubbleScreenLayout {
  // Единый стор метрик скана: один ResizeObserver живёт в ImageViewer,
  // а 25+ баблов лишь подписываются на готовые значения.
  const { naturalW, naturalH, clientH: displayH } = usePageImageMetrics()
  // Эпоха общая для всех кэшей вёрстки: при догрузке шрифта кэши чистятся,
  // а useMemo ниже пересчитывает переносы по реальным метрикам.
  const fontsEpoch = useFontsEpoch()

  const currentFont = box.fontFamily || "v_CCFaceFront"

  const display = useMemo(
    () =>
      computeBubbleDisplayLines(
        box,
        { naturalW, naturalH },
        defaultFontSize,
        currentW,
        currentH
      ),
    // fontsEpoch: шрифт мог догрузиться — пересчитываем метрики.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [box, defaultFontSize, currentW, currentH, naturalW, naturalH, fontsEpoch]
  )

  const screenLines = display.screenLines
  const editableLines = display.editableLines
  const masterActualFontSize = display.actualFontSize
  const masterLineHeight = display.lineHeight
  const masterBoxPixelH = currentH * naturalH

  const scale = naturalH > 0 ? displayH / naturalH : 1
  const finalScreenFontSize = Math.max(6, Number((masterActualFontSize * scale).toFixed(2)))
  const finalScreenLineHeight = Math.max(7, Number((masterLineHeight * scale).toFixed(2)))

  const computeReflowedState = (
    snapshotLines: string[],
    rawInput: string,
    options?: ReflowOptions
  ): BubbleReflowedState => {
    const trimmed = rawInput.trim()
    if (!trimmed) return { storageText: "" }
    return { storageText: reflowFromManualLines(snapshotLines, trimmed, options) }
  }

  return {
    screenLines,
    editableLines,
    finalScreenFontSize,
    finalScreenLineHeight,
    currentFont,
    masterBoxPixelH,
    screenScale: scale,
    computeReflowedState,
  }
}

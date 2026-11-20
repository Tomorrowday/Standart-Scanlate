// manga_ui/lib/typeset/layout/bubble-display-lines.ts
/**
 * Единый pure-helper расчёта видимых строк бабла для экрана и карточки.
 *
 * Раньше `use-bubble-screen-layout.ts` и `use-card-rus-editor.ts` дублировали
 * один и тот же расчёт кегля/вёрстки/проекции регистра. Теперь движок один,
 * а результаты кэшируются по ключу параметров (LRU).
 */

import type { TextBlock } from "@/lib/types"
import { layoutBubbleTextLines } from "./bubble-layout-engine"
import { FORCED_SINGLE_LINE_MARKER, projectLinesToOriginalCase } from "./manual-reflow"
import { registerLayoutCacheClearer } from "./fonts-epoch"

export interface BubbleDisplayMetrics {
  naturalW: number
  naturalH: number
}

export interface BubbleDisplayLines {
  /** Строки, которые рисуются на скане (UPPERCASE, если включён). */
  screenLines: string[]
  /** Строки для редактора (проекция на исходный регистр). */
  editableLines: string[]
  /** Итоговый кегль в координатах оригинала. */
  actualFontSize: number
  /** Итоговая высота строки в координатах оригинала. */
  lineHeight: number
}

const CACHE_LIMIT = 512
const cache = new Map<string, BubbleDisplayLines>()

// После загрузки шрифта ключ кэша не меняется, поэтому кэш нужно сбросить
// явно: иначе останутся переносы/кегль, посчитанные для fallback-шрифта.
registerLayoutCacheClearer(() => cache.clear())

let sharedCanvas: HTMLCanvasElement | null = null

function getSharedContext(): CanvasRenderingContext2D | null {
  if (typeof document === "undefined") return null
  if (!sharedCanvas) sharedCanvas = document.createElement("canvas")
  return sharedCanvas.getContext("2d")
}

function buildCacheKey(
  block: TextBlock,
  metrics: BubbleDisplayMetrics,
  defaultFontSize: number,
  boxW: number,
  boxH: number
): string {
  return [
    block.rusText || "",
    block.fontSize ?? "",
    block.fontFamily ?? "",
    block.shape ?? "",
    block.paddingMode ?? "",
    block.isBold ? 1 : 0,
    block.isItalic ? 1 : 0,
    block.isUppercase ? 1 : 0,
    block.minHyphens === false ? 0 : 1,
    defaultFontSize,
    metrics.naturalW,
    metrics.naturalH,
    boxW,
    boxH,
  ].join("\u0000")
}

/**
 * Считает вёрстку текста бабла в координатах оригинала.
 *
 * @param boxW нормированная ширина бабла (0..1) — для drag-состояния можно
 *             передавать актуальную ширину, а не из блока.
 * @param boxH нормированная высота бабла (0..1).
 */
export function computeBubbleDisplayLines(
  block: TextBlock,
  metrics: BubbleDisplayMetrics,
  defaultFontSize: number,
  boxW: number,
  boxH: number,
  ctx?: CanvasRenderingContext2D | null
): BubbleDisplayLines {
  const key = buildCacheKey(block, metrics, defaultFontSize, boxW, boxH)
  const cached = cache.get(key)
  if (cached) return cached

  const baseSize = block.fontSize || defaultFontSize
  const masterFontSize = Math.round(baseSize * (metrics.naturalH / 1200))
  const masterBoxPixelW = boxW * metrics.naturalW
  const masterBoxPixelH = boxH * metrics.naturalH
  const currentFont = block.fontFamily || "v_CCFaceFront"
  const padMode = block.paddingMode || "safe"
  const isMinHyphens = block.minHyphens !== false

  const raw = block.rusText || ""
  const displayText = block.isUppercase ? raw.toUpperCase() : raw

  const context = ctx ?? getSharedContext()
  if (!context || !displayText.trim() || masterBoxPixelW <= 0 || masterBoxPixelH <= 0) {
    const fallback: BubbleDisplayLines = {
      screenLines: [],
      editableLines: [],
      actualFontSize: masterFontSize,
      lineHeight: Math.round(masterFontSize * 1.15),
    }
    return fallback
  }

  const res = layoutBubbleTextLines(
    context,
    displayText,
    masterBoxPixelW,
    masterBoxPixelH,
    masterFontSize,
    currentFont,
    block.shape || "rect",
    padMode,
    block.isBold,
    block.isItalic,
    isMinHyphens
  )

  let editableLines = res.lines
  const rawForEdit = raw.split(FORCED_SINGLE_LINE_MARKER).join("")

  if (block.isUppercase && rawForEdit.trim()) {
    // Строки посчитаны по ширине UPPERCASE — проецируем на исходный регистр,
    // чтобы переносы в редакторе совпадали со сканом.
    const projected = projectLinesToOriginalCase(rawForEdit, res.lines)
    if (projected && projected.length > 0) {
      editableLines = projected
    } else {
      const rawRes = layoutBubbleTextLines(
        context,
        raw,
        masterBoxPixelW,
        masterBoxPixelH,
        masterFontSize,
        currentFont,
        block.shape || "rect",
        padMode,
        block.isBold,
        block.isItalic,
        isMinHyphens
      )
      editableLines = rawRes.lines
    }
  }

  const result: BubbleDisplayLines = {
    screenLines: res.lines,
    editableLines,
    actualFontSize: res.actualFontSize,
    lineHeight: res.lineHeight,
  }

  if (cache.size >= CACHE_LIMIT) cache.clear()
  cache.set(key, result)
  return result
}

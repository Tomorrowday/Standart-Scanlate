// manga_ui/components/image-viewer/jap-overlay-placement.ts
// Централизованный расчёт стартовых позиций плашек японского оригинала:
// - плашка не перекрывает свой и чужие баблы;
// - плашки не накладываются друг на друга;
// - плашка по возможности остаётся внутри страницы [0, 1].
// Ручное смещение (box.japOffset) применяется поверх вычисленной базовой позиции,
// поэтому кнопка сброса возвращает плашку именно в свободное место.

import type { TextBlock } from "@/lib/types"

/** Базовая оценка ширины плашки в нормализованных координатах страницы (0..1). */
const JAP_PLATE_WIDTH = 0.22
/** Высота плашки без текста (шапка + отступы) в нормализованных координатах. */
const JAP_PLATE_BASE_HEIGHT = 0.032
/** Прибавка высоты на каждую строку японского текста. */
const JAP_PLATE_LINE_HEIGHT = 0.022
/** Оценка габаритов плашки в пикселях (когда известен реальный размер скана). */
const PLATE_WIDTH_PX = 240
/** Шапка плашки (#1 JP + паддинги контейнера). */
const PLATE_HEADER_PX = 38
const PLATE_LINE_PX = 24
/** Максимальная оценка высоты плашки. */
const PLATE_MAX_HEIGHT_PX = 260
/** Отступ от бабла до плашки. */
const JAP_PLATE_GAP = 0.014
/** Шаги удаления от бабла: сначала рядом, затем дальше (сдвоенные и плотные баблы). */
const JAP_PLATE_DISTANCE_STEPS = [0, 0.05, 0.1, 0.16, 0.24]
/** Сколько символов японского текста помещается в строку плашки. */
const CHARS_PER_LINE = 11
const MAX_ESTIMATED_LINES = 12
const MIN_BOX_SIZE = 0.001

/** Реальный размер отрисованного скана в пикселях (для перевода габаритов в 0..1). */
export interface JapPlateImageMetrics {
  width: number
  height: number
}

/** Веса штрафов: перекрытие бабла/плашки и выход за границы страницы. */
const BUBBLE_COLLISION_WEIGHT = 5000
const PLATE_COLLISION_WEIGHT = 8000
const OUT_OF_BOUNDS_WEIGHT = 4000

export type JapPlateSide = "right" | "left" | "bottom" | "top"

export interface JapPlatePlacement {
  /** Левый край плашки, нормализованный по странице (0..1). */
  x: number
  /** Верхний край плашки, нормализованный по странице (0..1). */
  y: number
  /** Оценка ширины плашки (0..1). */
  width: number
  /** Оценка высоты плашки (0..1). */
  height: number
  /** Сторона бабла, с которой стоит плашка. */
  side: JapPlateSide
}

export type JapPlatePlacements = Record<string, JapPlatePlacement>

interface Rect {
  x: number
  y: number
  width: number
  height: number
}

interface Candidate {
  x: number
  y: number
  side: JapPlateSide
  /** Небольшой бонус за привычное расположение рядом со своим баблом. */
  basePenalty: number
}

function toRect(box: TextBlock): Rect {
  return {
    x: box.x,
    y: box.y,
    width: Math.max(box.width, MIN_BOX_SIZE),
    height: Math.max(box.height, MIN_BOX_SIZE),
  }
}

/** Оценка габаритов плашки по её тексту (стандартные пропорции из макета). */
export function estimateJapPlateSize(
  japText: string,
  image?: JapPlateImageMetrics | null
): { width: number; height: number } {
  const compact = (japText || "").replace(/\s+/g, "")
  const lines = Math.min(
    MAX_ESTIMATED_LINES,
    Math.max(1, Math.ceil(compact.length / CHARS_PER_LINE))
  )

  if (image && image.width > 0 && image.height > 0) {
    const widthPx = compact.length <= 8 ? PLATE_WIDTH_PX * 0.75 : PLATE_WIDTH_PX
    const heightPx = Math.min(PLATE_MAX_HEIGHT_PX, PLATE_HEADER_PX + lines * PLATE_LINE_PX)
    return {
      width: Math.min(0.45, Math.max(0.12, widthPx / image.width)),
      height: Math.min(0.6, Math.max(0.04, heightPx / image.height)),
    }
  }

  return {
    width: JAP_PLATE_WIDTH,
    height: JAP_PLATE_BASE_HEIGHT + lines * JAP_PLATE_LINE_HEIGHT,
  }
}

/** Площадь пересечения двух прямоугольников. */
function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

/** Площадь части прямоугольника, вышедшей за пределы страницы [0, 1]x[0, 1]. */
function outOfBoundsArea(r: Rect): number {
  const insideW = Math.max(0, Math.min(r.x + r.width, 1) - Math.max(r.x, 0))
  const insideH = Math.max(0, Math.min(r.y + r.height, 1) - Math.max(r.y, 0))
  return Math.max(0, r.width * r.height - insideW * insideH)
}

/** Кандидаты размещения вокруг бабла: привычные стороны + сдвинутые дальше от бабла. */
function buildCandidates(rect: Rect, width: number, height: number): Candidate[] {
  const centerX = rect.x + rect.width / 2 - width / 2
  const bottomY = rect.y + rect.height + JAP_PLATE_GAP
  const topY = rect.y - height - JAP_PLATE_GAP
  const candidates: Candidate[] = []

  // Плашка всегда остаётся внутри страницы, иначе появляются лишние скроллбары
  const maxX = Math.max(0, 1 - width)
  const maxY = Math.max(0, 1 - height)
  const clampX = (x: number) => Math.min(Math.max(x, 0), maxX)
  const clampY = (y: number) => Math.min(Math.max(y, 0), maxY)

  JAP_PLATE_DISTANCE_STEPS.forEach((extra, stepIndex) => {
    // Чем дальше плашка от своего бабла, тем неохотнее её выбираем
    const drift = stepIndex * 3
    const rightX = rect.x + rect.width + JAP_PLATE_GAP + extra
    const leftX = rect.x - width - JAP_PLATE_GAP - extra
    const bottomAlignedY = rect.y + rect.height - height

    candidates.push(
      { x: clampX(rightX), y: clampY(rect.y), side: "right", basePenalty: drift },
      { x: clampX(leftX), y: clampY(rect.y), side: "left", basePenalty: drift + 0.5 },
      {
        x: clampX(rightX),
        y: clampY(bottomAlignedY),
        side: "right",
        basePenalty: drift + 2,
      },
      {
        x: clampX(leftX),
        y: clampY(bottomAlignedY),
        side: "left",
        basePenalty: drift + 2.5,
      },
      {
        x: clampX(centerX),
        y: clampY(bottomY + extra),
        side: "bottom",
        basePenalty: drift + 5,
      },
      {
        x: clampX(centerX),
        y: clampY(topY - extra),
        side: "top",
        basePenalty: drift + 5,
      }
    )
  })

  // Крайний случай: по центру своего бабла (лучше перекрыть его, чем улететь за страницу)
  candidates.push({
    x: clampX(centerX),
    y: clampY(rect.y + rect.height / 2 - height / 2),
    side: "right",
    basePenalty: 40,
  })

  return candidates
}

function scoreCandidate(
  candidate: Candidate,
  width: number,
  height: number,
  bubbles: Rect[],
  placedPlates: Rect[]
): number {
  const plate: Rect = { x: candidate.x, y: candidate.y, width, height }

  let penalty = candidate.basePenalty
  for (const bubble of bubbles) {
    penalty += overlapArea(plate, bubble) * BUBBLE_COLLISION_WEIGHT
  }
  for (const placed of placedPlates) {
    penalty += overlapArea(plate, placed) * PLATE_COLLISION_WEIGHT
  }
  penalty += outOfBoundsArea(plate) * OUT_OF_BOUNDS_WEIGHT

  return penalty
}

/**
 * Считает базовую позицию плашки JP для каждого бабла с непустым japText.
 * Чистая функция: результат зависит только от геометрии и текста баблов.
 */
export function computeJapPlatePlacements(
  boxes: TextBlock[],
  image?: JapPlateImageMetrics | null
): JapPlatePlacements {
  const bubbles = boxes.filter((box) => box.id !== "__draft__").map(toRect)
  const placedPlates: Rect[] = []
  const placements: JapPlatePlacements = {}

  for (const box of boxes) {
    if (box.id === "__draft__") continue
    const japText = (box.japText || "").trim()
    if (!japText) continue

    const { width, height } = estimateJapPlateSize(japText, image)
    const rect = toRect(box)

    let best: { candidate: Candidate; penalty: number } | null = null
    for (const candidate of buildCandidates(rect, width, height)) {
      const penalty = scoreCandidate(candidate, width, height, bubbles, placedPlates)
      if (!best || penalty < best.penalty - 1e-6) {
        best = { candidate, penalty }
      }
    }

    if (!best) continue

    placements[box.id] = {
      x: best.candidate.x,
      y: best.candidate.y,
      width,
      height,
      side: best.candidate.side,
    }
    placedPlates.push({ x: best.candidate.x, y: best.candidate.y, width, height })
  }

  return placements
}

// manga_ui/__tests__/jap-overlay-placement.test.ts
import { describe, expect, it } from "vitest"

import type { TextBlock } from "@/lib/types"
import {
  computeJapPlatePlacements,
  estimateJapPlateSize,
} from "@/components/image-viewer/jap-overlay-placement"

function box(
  id: string,
  x: number,
  y: number,
  width: number,
  height: number,
  japText: string
): TextBlock {
  return {
    id,
    class_id: 0,
    x,
    y,
    width,
    height,
    rotation: 0,
    japText,
    rusText: "",
    speaker: "",
    orderIndex: 1,
    status: "new",
    fontFamily: "v_CCFaceFront",
    isBold: false,
    isItalic: false,
    isUppercase: false,
    hasStroke: false,
    textColor: "black",
    shape: "rect",
    paddingMode: "safe",
    minHyphens: true,
  }
}

function overlaps(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number }
): boolean {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y)
  return w > 0.0001 && h > 0.0001
}

describe("estimateJapPlateSize", () => {
  it("учитывает явные переносы строк и делает плашку выше", () => {
    const single = estimateJapPlateSize("こんにちは")
    const multiline = estimateJapPlateSize("こんにちは\nさようなら")

    expect(multiline.height).toBeGreaterThan(single.height)
    expect(single.width).toBeGreaterThan(0)
  })

  it("использует размеры скана, если они известны", () => {
    const withImage = estimateJapPlateSize("こんにちは", { width: 1200, height: 1600 })
    const withoutImage = estimateJapPlateSize("こんにちは")

    expect(withImage.width).toBeGreaterThan(0)
    expect(withImage.height).toBeGreaterThan(0)
    expect(withImage.width).toBeLessThanOrEqual(0.45)
    expect(withoutImage.width).toBeCloseTo(0.22)
  })
})

describe("computeJapPlatePlacements", () => {
  it("ставит плашки рядом с баблами, не перекрывая их и друг друга", () => {
    const boxes = [
      box("b1", 0.05, 0.05, 0.2, 0.12, "こんにちは"),
      box("b2", 0.7, 0.7, 0.2, 0.12, "さようなら"),
    ]

    const placements = computeJapPlatePlacements(boxes)

    expect(Object.keys(placements).sort()).toEqual(["b1", "b2"])
    for (const rect of Object.values(placements)) {
      expect(rect.x).toBeGreaterThanOrEqual(0)
      expect(rect.y).toBeGreaterThanOrEqual(0)
      expect(rect.x + rect.width).toBeLessThanOrEqual(1.000001)
      expect(rect.y + rect.height).toBeLessThanOrEqual(1.000001)
    }
    expect(overlaps(placements.b1, placements.b2)).toBe(false)
    expect(overlaps(placements.b1, boxes[0])).toBe(false)
    expect(overlaps(placements.b2, boxes[1])).toBe(false)
  })

  it("не создаёт плашки для пустого japText и черновика", () => {
    const placements = computeJapPlatePlacements([
      box("empty", 0.1, 0.1, 0.2, 0.1, ""),
      box("spaces", 0.3, 0.1, 0.2, 0.1, "   "),
      box("__draft__", 0.5, 0.1, 0.2, 0.1, "テスト"),
      box("real", 0.6, 0.6, 0.2, 0.1, "テスト"),
    ])

    expect(Object.keys(placements)).toEqual(["real"])
  })

  it("учитывает явные переносы строк при оценке габаритов", () => {
    const placements = computeJapPlatePlacements([
      box("multi", 0.2, 0.2, 0.2, 0.1, "一行目\n二行目\n三行目"),
    ])

    expect(placements.multi.height).toBeGreaterThan(
      estimateJapPlateSize("一行目").height
    )
  })
})

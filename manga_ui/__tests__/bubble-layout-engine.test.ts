// manga_ui/__tests__/bubble-layout-engine.test.ts
import { describe, expect, it } from "vitest"

import { layoutBubbleTextLines } from "@/lib/typeset/layout/bubble-layout-engine"
import { getEllipseWidthAtY } from "@/lib/typeset/layout/ellipse-geometry"
import { FORCED_SINGLE_LINE_MARKER } from "@/lib/typeset/layout/manual-reflow"

/** Лёгкий макет Canvas-контекста: ширина символа пропорциональна кеглю из ctx.font. */
function makeCtx(charWidthRatio = 0.55): CanvasRenderingContext2D {
  let font = "16px 'test', sans-serif"
  return {
    get font() {
      return font
    },
    set font(value: string) {
      font = value
    },
    measureText(text: string) {
      const size = Number.parseFloat(font) || 16
      const width = Array.from(text).length * size * charWidthRatio
      return { width } as TextMetrics
    },
  } as unknown as CanvasRenderingContext2D
}

describe("getEllipseWidthAtY", () => {
  it("сужается к полюсам и не уходит ниже 58% радиуса", () => {
    expect(getEllipseWidthAtY(0, 100, 50)).toBeCloseTo(200)
    expect(getEllipseWidthAtY(40, 100, 50)).toBeCloseTo(120)
    expect(getEllipseWidthAtY(50, 100, 50)).toBeCloseTo(58)
    expect(getEllipseWidthAtY(90, 100, 50)).toBeCloseTo(58)
    expect(getEllipseWidthAtY(0, 100, 0)).toBeCloseTo(58)
  })
})

describe("layoutBubbleTextLines", () => {
  it("автоматически раскладывает текст и не превышает заданный кегль", () => {
    const result = layoutBubbleTextLines(
      makeCtx(),
      "Привет мир как дела",
      240,
      200,
      18,
      "test",
      "rect",
      "safe",
      false,
      false,
      false
    )

    expect(result.lines.length).toBeGreaterThan(0)
    expect(result.actualFontSize).toBeLessThanOrEqual(18)
    expect(result.actualFontSize).toBeGreaterThanOrEqual(8)
    expect(result.lineHeight).toBe(Math.round(result.actualFontSize * 1.15))
  })

  it("сохраняет ручные переносы строк пользователя", () => {
    const result = layoutBubbleTextLines(
      makeCtx(),
      "Первая строка\nВторая строка",
      400,
      300,
      16,
      "test",
      "rect",
      "safe",
      false,
      false,
      true
    )

    expect(result.lines).toEqual(["Первая строка", "Вторая строка"])
  })

  it("принудительная одна строка уменьшает кегль вместо автопереноса", () => {
    const result = layoutBubbleTextLines(
      makeCtx(),
      `Привет${FORCED_SINGLE_LINE_MARKER}`,
      100,
      200,
      30,
      "test",
      "rect",
      "safe",
      false,
      false,
      true
    )

    expect(result.lines).toEqual(["Привет"])
    expect(result.actualFontSize).toBeLessThan(30)
    expect(result.actualFontSize).toBeGreaterThanOrEqual(8)
  })

  it("овальный бабл даёт не меньше строк, чем прямоугольный", () => {
    const text = "Очень длинный текст для овального бабла"
    const rect = layoutBubbleTextLines(
      makeCtx(), text, 300, 240, 20, "test", "rect", "safe", false, false, false
    )
    const ellipse = layoutBubbleTextLines(
      makeCtx(), text, 300, 240, 20, "test", "ellipse", "safe", false, false, false
    )

    expect(ellipse.lines.length).toBeGreaterThanOrEqual(rect.lines.length)
    expect(ellipse.actualFontSize).toBeLessThanOrEqual(20)
  })

  it("никогда не опускает кегль ниже 8", () => {
    const result = layoutBubbleTextLines(
      makeCtx(),
      "Очень длинное слово которое точно не поместится в крошечный бабл",
      40,
      30,
      20,
      "test",
      "rect",
      "fit",
      true,
      true,
      true
    )

    expect(result.actualFontSize).toBe(8)
    expect(result.lines.length).toBeGreaterThan(0)
  })

  it("fit-режим допускает чуть более широкие строки, чем safe", () => {
    const text = "Строка для проверки ширины"
    const safe = layoutBubbleTextLines(
      makeCtx(), text, 220, 200, 22, "test", "rect", "safe", false, false, false
    )
    const fit = layoutBubbleTextLines(
      makeCtx(), text, 220, 200, 22, "test", "rect", "fit", false, false, false
    )

    expect(fit.actualFontSize).toBeGreaterThanOrEqual(safe.actualFontSize)
  })
})

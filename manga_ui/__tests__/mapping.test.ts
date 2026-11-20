// manga_ui/__tests__/mapping.test.ts
import { describe, expect, it } from "vitest"

import {
  compareMangaBlocks,
  insertBlockInMangaOrder,
  mapDbBlockToTextBlock,
} from "@/lib/typeset/mapping"
import type { TextBlock } from "@/lib/types"

function block(id: string, x: number, y: number, w = 0.2, h = 0.1): TextBlock {
  return {
    id,
    class_id: 0,
    x,
    y,
    width: w,
    height: h,
    rotation: 0,
    japText: "",
    rusText: "",
    speaker: "",
    orderIndex: 0,
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

describe("mapDbBlockToTextBlock", () => {
  it("преобразует строку БД и font_size=null в undefined (режим Auto)", () => {
    const mapped = mapDbBlockToTextBlock({
      id: 42,
      class_id: 1,
      x: 0.1,
      y: 0.2,
      width: 0.3,
      height: 0.4,
      rotation: 0,
      jap_text: "こんにちは",
      rus_text: "Привет",
      speaker: "Макима",
      order_index: 3,
      font_size: null,
      font_family: "v_Augie",
      is_bold: 1,
      is_italic: 0,
      is_uppercase: 1,
      has_stroke: 1,
      text_color: "white",
      shape: "ellipse",
      padding_mode: "fit",
      min_hyphens: 0,
      status: "translated",
    })

    expect(mapped.id).toBe("42")
    expect(mapped.fontSize).toBeUndefined()
    expect(mapped.japText).toBe("こんにちは")
    expect(mapped.rusText).toBe("Привет")
    expect(mapped.isBold).toBe(true)
    expect(mapped.textColor).toBe("white")
    expect(mapped.shape).toBe("ellipse")
    expect(mapped.paddingMode).toBe("fit")
    expect(mapped.minHyphens).toBe(false)
  })

  it("сохраняет числовой и строковый font_size", () => {
    expect(mapDbBlockToTextBlock({ id: "a", font_size: 18 }).fontSize).toBe(18)
    expect(mapDbBlockToTextBlock({ id: "b", font_size: "16" }).fontSize).toBe(16)
  })

  it("выводит статус из текста, если status не задан", () => {
    expect(mapDbBlockToTextBlock({ id: "a", rus_text: "Перевод" }).status).toBe("translated")
    expect(mapDbBlockToTextBlock({ id: "b", jap_text: "原文" }).status).toBe("ocr-done")
    expect(mapDbBlockToTextBlock({ id: "c" }).status).toBe("new")
  })

  it("подставляет безопасные значения по умолчанию", () => {
    const mapped = mapDbBlockToTextBlock({ id: "x", x: null, y: undefined })
    expect(mapped.x).toBe(0)
    expect(mapped.y).toBe(0)
    expect(mapped.fontFamily).toBe("v_CCFaceFront")
    expect(mapped.minHyphens).toBe(true)
  })
})

describe("compareMangaBlocks", () => {
  it("в одном ряду читает справа налево", () => {
    const left = block("left", 0.1, 0.1)
    const right = block("right", 0.6, 0.1)

    // Положительный результат: left идёт после right.
    expect(compareMangaBlocks(left, right)).toBeGreaterThan(0)
    expect(compareMangaBlocks(right, left)).toBeLessThan(0)
  })

  it("разные ряды читает сверху вниз", () => {
    const top = block("top", 0.1, 0.1)
    const bottom = block("bottom", 0.1, 0.6)

    expect(compareMangaBlocks(top, bottom)).toBeLessThan(0)
    expect(compareMangaBlocks(bottom, top)).toBeGreaterThan(0)
  })
})

describe("insertBlockInMangaOrder", () => {
  it("вставляет правый блок перед левым и перенумеровывает orderIndex", () => {
    const left = { ...block("left", 0.1, 0.1), orderIndex: 1 }

    const result = insertBlockInMangaOrder([left], block("right", 0.6, 0.1))

    expect(result.map((b) => b.id)).toEqual(["right", "left"])
    expect(result.map((b) => b.orderIndex)).toEqual([1, 2])
  })

  it("вставляет верхний блок перед нижним", () => {
    const bottom = { ...block("bottom", 0.1, 0.6), orderIndex: 1 }
    const result = insertBlockInMangaOrder([bottom], block("top", 0.1, 0.1))

    expect(result.map((b) => b.id)).toEqual(["top", "bottom"])
  })
})

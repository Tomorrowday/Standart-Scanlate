// manga_ui/__tests__/hyphenation.test.ts
import { describe, expect, it } from "vitest"

import { appendHyphenSafe, cleanLeadingPunct, getWordHyphenSplits } from "@/lib/typeset/hyphenation"

describe("getWordHyphenSplits", () => {
  it("разбивает русское слово на слоги и ставит дефис только в prefix", () => {
    const splits = getWordHyphenSplits("молоко")
    const prefixes = splits.map((s) => s.prefix)

    expect(prefixes).toContain("мо-")
    expect(prefixes).toContain("моло-")
    for (const split of splits) {
      expect(split.prefix.endsWith("-")).toBe(true)
      expect(split.suffix.length).toBeGreaterThan(0)
      expect(split.isNativeHyphen).toBe(false)
    }
  })

  it("не отрывает ь/ъ/й от предыдущей буквы", () => {
    const splits = getWordHyphenSplits("мальчик")

    expect(splits.map((s) => s.prefix)).toContain("маль-")
    for (const split of splits) {
      expect(split.suffix.startsWith("ь")).toBe(false)
      expect(split.suffix.startsWith("ъ")).toBe(false)
      expect(split.suffix.startsWith("й")).toBe(false)
    }
  })

  it("переносит после й перед согласной (вой-на)", () => {
    expect(getWordHyphenSplits("война").map((s) => s.prefix)).toContain("вой-")
  })

  it("делит удвоенные согласные (груп-па, мас-са)", () => {
    expect(getWordHyphenSplits("группа").map((s) => s.prefix)).toContain("груп-")
    expect(getWordHyphenSplits("масса").map((s) => s.prefix)).toContain("мас-")
  })

  it("сохраняет естественный дефис составного слова", () => {
    const splits = getWordHyphenSplits("кто-то")
    const native = splits.find((s) => s.isNativeHyphen)

    expect(native).toBeDefined()
    expect(native?.prefix).toBe("кто-")
    expect(native?.suffix).toBe("то")
  })

  it("дефисные слова с длинными частями получают и слоговые, и естественный перенос", () => {
    const splits = getWordHyphenSplits("светло-синий")
    expect(splits.some((s) => s.isNativeHyphen && s.prefix === "светло-")).toBe(true)
    expect(splits.some((s) => !s.isNativeHyphen)).toBe(true)
  })

  it("короткие слова не переносятся", () => {
    expect(getWordHyphenSplits("дом")).toEqual([])
    expect(getWordHyphenSplits("")).toEqual([])
  })
})

describe("appendHyphenSafe", () => {
  it("добавляет дефис к обычному слову", () => {
    expect(appendHyphenSafe("слово")).toBe("слово-")
  })

  it("не дублирует дефис и не добавляет его после пунктуации", () => {
    expect(appendHyphenSafe("слово-")).toBe("слово-")
    expect(appendHyphenSafe("слово,")).toBe("слово,")
    expect(appendHyphenSafe("слово!")).toBe("слово!")
    expect(appendHyphenSafe("слово…")).toBe("слово…")
    expect(appendHyphenSafe("«слово»")).toBe("«слово»")
  })

  it("обрезает хвостовые пробелы и корректно обрабатывает пустую строку", () => {
    expect(appendHyphenSafe("слово   ")).toBe("слово-")
    expect(appendHyphenSafe("")).toBe("")
  })
})

describe("cleanLeadingPunct", () => {
  it("снимает тире и пробелы в начале продолжения строки", () => {
    expect(cleanLeadingPunct("-слово")).toBe("слово")
    expect(cleanLeadingPunct("— Привет")).toBe("Привет")
    expect(cleanLeadingPunct("  –слово")).toBe("слово")
  })

  it("одиночное тире не исчезает полностью", () => {
    expect(cleanLeadingPunct("—")).toBe("—")
    expect(cleanLeadingPunct("  -  ")).toBe("-")
  })

  it("обычное слово не трогает", () => {
    expect(cleanLeadingPunct("слово")).toBe("слово")
  })
})

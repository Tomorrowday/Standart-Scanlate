// manga_ui/__tests__/compound-words.test.ts
import { describe, expect, it } from "vitest"

import {
  isCompoundHyphenPair,
  joinLinesRemovingSoftHyphens,
} from "@/lib/typeset/layout/compound-words"

describe("isCompoundHyphenPair", () => {
  it("узнаёт японские именные суффиксы", () => {
    expect(isCompoundHyphenPair("Наруто", "кун")).toBe(true)
    expect(isCompoundHyphenPair("Макима", "сан")).toBe(true)
    expect(isCompoundHyphenPair("Ямада", "сэмпай")).toBe(true)
    expect(isCompoundHyphenPair("Аяка", "тян")).toBe(true)
  })

  it("узнаёт постфиксы и частицы", () => {
    expect(isCompoundHyphenPair("кто", "то")).toBe(true)
    expect(isCompoundHyphenPair("какой", "нибудь")).toBe(true)
    expect(isCompoundHyphenPair("как", "либо")).toBe(true)
    expect(isCompoundHyphenPair("всё", "таки")).toBe(true)
    expect(isCompoundHyphenPair("ну", "ка")).toBe(true)
  })

  it("узнаёт повторы и короткие вставки (точь-в-точь)", () => {
    expect(isCompoundHyphenPair("точь-в", "точь")).toBe(true)
    expect(isCompoundHyphenPair("еле", "еле")).toBe(true)
    expect(isCompoundHyphenPair("чуть", "чуть")).toBe(true)
  })

  it("узнаёт сложные прилагательные (светло-синий)", () => {
    expect(isCompoundHyphenPair("светло", "синий")).toBe(true)
    expect(isCompoundHyphenPair("юго", "запад")).toBe(true)
    expect(isCompoundHyphenPair("чудо", "оружие")).toBe(true)
  })

  it("узнаёт двойные имена и фамилии по заглавной букве", () => {
    expect(isCompoundHyphenPair("Римский", "Корсаков")).toBe(true)
    expect(isCompoundHyphenPair("Анна", "Мария")).toBe(true)
    expect(isCompoundHyphenPair("Санкт", "Петербург")).toBe(true)
  })

  it("не считает мягкий слоговой перенос составным словом", () => {
    expect(isCompoundHyphenPair("При", "вет")).toBe(false)
    expect(isCompoundHyphenPair("обыч", "ный")).toBe(false)
    expect(isCompoundHyphenPair("", "то")).toBe(false)
  })
})

describe("joinLinesRemovingSoftHyphens", () => {
  it("склеивает мягкий перенос без дефиса", () => {
    expect(joinLinesRemovingSoftHyphens(["При-", "вет"])).toBe("Привет")
    expect(joinLinesRemovingSoftHyphens(["Подож-", "дите"])).toBe("Подождите")
  })

  it("сохраняет дефис в составных словах и именах", () => {
    expect(joinLinesRemovingSoftHyphens(["кто-", "то"])).toBe("кто-то")
    expect(joinLinesRemovingSoftHyphens(["светло-", "синий"])).toBe("светло-синий")
    expect(joinLinesRemovingSoftHyphens(["Римский-", "Корсаков"])).toBe("Римский-Корсаков")
    expect(joinLinesRemovingSoftHyphens(["точь-в-", "точь"])).toBe("точь-в-точь")
    expect(joinLinesRemovingSoftHyphens(["Ямада-", "сэмпай"])).toBe("Ямада-сэмпай")
  })

  it("склеивает обычные строки через пробел и пропускает пустые", () => {
    expect(joinLinesRemovingSoftHyphens(["Первая строка", "вторая"])).toBe("Первая строка вторая")
    expect(joinLinesRemovingSoftHyphens(["При-", "", "вет"])).toBe("Привет")
    expect(joinLinesRemovingSoftHyphens([])).toBe("")
  })

  it("не склеивает длинное тире и дефис с пробелом", () => {
    expect(joinLinesRemovingSoftHyphens(["слово —", "дальше"])).toBe("слово — дальше")
    expect(joinLinesRemovingSoftHyphens(["слово -", "дальше"])).toBe("слово - дальше")
  })
})

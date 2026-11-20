// manga_ui/__tests__/manual-reflow.test.ts
import { describe, expect, it } from "vitest"

import {
  FORCED_SINGLE_LINE_MARKER,
  hasManualLineBreaks,
  hasModifiedLineBreaks,
  projectLinesToOriginalCase,
  reflowFromManualLines,
  stripForcedSingleLineMarker,
} from "@/lib/typeset/layout/manual-reflow"

describe("FORCED_SINGLE_LINE_MARKER", () => {
  it("это невидимый Word Joiner U+2060", () => {
    expect(FORCED_SINGLE_LINE_MARKER).toBe("\u2060")
    expect(FORCED_SINGLE_LINE_MARKER).toHaveLength(1)
  })
})

describe("hasManualLineBreaks / stripForcedSingleLineMarker", () => {
  it("видит перевод строки и невидимый маркер", () => {
    expect(hasManualLineBreaks("Первая\nВторая")).toBe(true)
    expect(hasManualLineBreaks(`Одна строка${FORCED_SINGLE_LINE_MARKER}`)).toBe(true)
    expect(hasManualLineBreaks("Обычный текст")).toBe(false)
    expect(hasManualLineBreaks(null)).toBe(false)
  })

  it("убирает маркер из текста для textarea", () => {
    expect(stripForcedSingleLineMarker(`Текст${FORCED_SINGLE_LINE_MARKER}`)).toBe("Текст")
    expect(stripForcedSingleLineMarker(null)).toBe("")
  })
})

describe("hasModifiedLineBreaks", () => {
  it("фиксирует изменение числа строк", () => {
    expect(hasModifiedLineBreaks(["a", "b"], "a\nb\nc", 2, false)).toBe(true)
  })

  it("фиксирует перераспределение слов при ручном Enter", () => {
    expect(hasModifiedLineBreaks(["a b", "c d"], "a\nb c d", 2, true)).toBe(true)
    expect(hasModifiedLineBreaks(["a b", "c d"], "a b\nc d", 2, true)).toBe(false)
  })

  it("без правки переносов и при том же числе строк считает блок авто", () => {
    expect(hasModifiedLineBreaks(["a b", "c d"], "a b\nc d", 2, false)).toBe(false)
  })
})

describe("reflowFromManualLines", () => {
  it("в авто-режиме склеивает строки обратно в один поток", () => {
    expect(
      reflowFromManualLines(["Привет", "как дела"], "Привет\nкак дела", {
        wasManualBeforeEdit: false,
      })
    ).toBe("Привет как дела")
  })

  it("в авто-режиме убирает мягкий слоговой перенос", () => {
    expect(
      reflowFromManualLines(["При-", "вет"], "При-\nвет", {
        wasManualBeforeEdit: false,
      })
    ).toBe("Привет")
  })

  it("сохраняет ручные переносы строк", () => {
    expect(
      reflowFromManualLines(["Привет", "как дела"], "Привет\nкак дела", {
        wasManualBeforeEdit: true,
      })
    ).toBe("Привет\nкак дела")
  })

  it("ставит маркер однострочности, если пользователь свёл несколько строк в одну", () => {
    expect(
      reflowFromManualLines(["Привет", "мир"], "Привет мир", {
        wasManualBeforeEdit: true,
      })
    ).toBe(`Привет мир${FORCED_SINGLE_LINE_MARKER}`)
  })

  it("восстанавливает маркер, если он был до правки", () => {
    expect(
      reflowFromManualLines(["Привет"], "Привет", {
        wasManualBeforeEdit: true,
        hadForcedSingleLine: true,
      })
    ).toBe(`Привет${FORCED_SINGLE_LINE_MARKER}`)
  })

  it("не теряет уже присутствующий маркер во входном тексте", () => {
    expect(
      reflowFromManualLines(["Текст"], `Текст${FORCED_SINGLE_LINE_MARKER}`, {
        wasManualBeforeEdit: true,
      })
    ).toBe(`Текст${FORCED_SINGLE_LINE_MARKER}`)
  })

  it("пустой текст даёт пустую строку", () => {
    expect(reflowFromManualLines(["Было"], "   \n  ", true)).toBe("")
  })

  it("не склеивает настоящее дефисное слово при переносе строки", () => {
    expect(
      reflowFromManualLines(["Ямада-", "сэмпай"], "Ямада-\nсэмпай", {
        wasManualBeforeEdit: true,
      })
    ).toBe("Ямада-\nсэмпай")
  })
})

describe("projectLinesToOriginalCase", () => {
  it("возвращает исходный регистр для UPPERCASE-строк", () => {
    expect(projectLinesToOriginalCase("Привет Мир", ["ПРИВЕТ", "МИР"])).toEqual([
      "Привет",
      "Мир",
    ])
  })

  it("сохраняет вставленные движком мягкие дефисы", () => {
    expect(projectLinesToOriginalCase("Привет", ["При-", "вет"])).toEqual(["При-", "вет"])
  })

  it("возвращает null, если строки не соответствуют исходному тексту", () => {
    expect(projectLinesToOriginalCase("Привет", ["Пока"])).toBeNull()
    expect(projectLinesToOriginalCase("Привет", ["Привет", "Лишнее"])).toBeNull()
  })
})

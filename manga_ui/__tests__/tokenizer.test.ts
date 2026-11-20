// manga_ui/__tests__/tokenizer.test.ts
import { describe, expect, it } from "vitest"

import {
  cleanAndTrimLines,
  tokenizeMangaPhrase,
} from "@/lib/typeset/layout/tokenizer"

describe("tokenizeMangaPhrase", () => {
  it("приклеивает тире в начале реплики к первому слову", () => {
    const { tokens, joinWithoutSpaceAfter } = tokenizeMangaPhrase("— Привет, как дела")

    expect(tokens).toEqual(["— Привет,", "как", "дела"])
    expect(joinWithoutSpaceAfter).toEqual([false, false, false])
  })

  it("приклеивает частицы ли/же/бы к предыдущему слову, а тире внутри фразы — тоже", () => {
    expect(tokenizeMangaPhrase("Ты же знаешь").tokens).toEqual(["Ты же", "знаешь"])
    expect(tokenizeMangaPhrase("Пришёл бы домой").tokens).toEqual(["Пришёл бы", "домой"])
    expect(tokenizeMangaPhrase("Скажи ли мне").tokens).toEqual(["Скажи ли", "мне"])
    expect(tokenizeMangaPhrase("Привет — как дела").tokens).toEqual([
      "Привет —",
      "как",
      "дела",
    ])
  })

  it("делит дефисные слова на переносимые части без пробела", () => {
    const simple = tokenizeMangaPhrase("Ямада-сэмпай")
    expect(simple.tokens).toEqual(["Ямада-", "сэмпай"])
    expect(simple.joinWithoutSpaceAfter).toEqual([true, false])

    const triple = tokenizeMangaPhrase("точь-в-точь")
    expect(triple.tokens).toEqual(["точь-в-", "точь"])
    expect(triple.joinWithoutSpaceAfter).toEqual([true, false])

    const many = tokenizeMangaPhrase("кто-нибудь-то")
    expect(many.tokens).toEqual(["кто-", "нибудь-", "то"])
    expect(many.joinWithoutSpaceAfter).toEqual([true, true, false])
  })

  it("не сваривает предлоги со следующим словом", () => {
    expect(tokenizeMangaPhrase("из дома").tokens).toEqual(["из", "дома"])
  })

  it("пустая строка даёт пустой результат", () => {
    expect(tokenizeMangaPhrase("   ")).toEqual({ tokens: [], joinWithoutSpaceAfter: [] })
  })
})

describe("cleanAndTrimLines", () => {
  it("приклеивает висячую пунктуацию к предыдущей строке", () => {
    expect(cleanAndTrimLines(["Первая", "...", "Вторая"])).toEqual([
      "Первая...",
      "Вторая",
    ])
  })

  it("приклеивает одиночное тире к предыдущей строке через пробел", () => {
    expect(cleanAndTrimLines(["Первая", "—", "Вторая"])).toEqual([
      "Первая —",
      "Вторая",
    ])
  })

  it("удаляет пустые строки, но сохраняет единственную пустую строку", () => {
    expect(cleanAndTrimLines(["a", "", "b"])).toEqual(["a", "b"])
    expect(cleanAndTrimLines([""])).toEqual([""])
  })

  it("обрезает пробелы по краям", () => {
    expect(cleanAndTrimLines(["  текст  "])).toEqual(["текст"])
  })
})

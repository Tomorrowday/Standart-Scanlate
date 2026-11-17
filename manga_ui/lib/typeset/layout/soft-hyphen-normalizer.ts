// manga_ui/lib/typeset/layout/soft-hyphen-normalizer.ts
// Разбор и нормализация мягких слоговых переносов между строками:
// склейка разорванного слова и снятие «висячего» дефиса старой вёрстки

import { isCompoundHyphenPair } from "./compound-words"

export interface SoftHyphenPair {
  left: string
  right: string
}

interface SoftHyphenBreak {
  pair: SoftHyphenPair
  lastWord: string
  leftStem: string
  firstWord: string
  restNext: string
  prevLineWithoutLastWord: string
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

export function parseSoftHyphenBreak(prevLineRaw: string, nextLineRaw: string): SoftHyphenBreak | null {
  const prevLine = (prevLineRaw || "").trim()
  const nextLine = (nextLineRaw || "").trim()
  if (!prevLine || !nextLine) return null

  const prevWords = prevLine.split(/\s+/)
  const lastWord = prevWords[prevWords.length - 1] || ""
  if (
    !lastWord.endsWith("-") ||
    lastWord.endsWith(" -") ||
    lastWord.endsWith("—") ||
    lastWord.endsWith("–")
  ) {
    return null
  }

  const leftStem = lastWord.slice(0, -1)
  if (!leftStem) return null

  const firstWord = nextLine.split(/\s+/)[0] || ""
  if (!firstWord) return null

  // isCompoundHyphenPair сам срезает окружающую пунктуацию
  if (isCompoundHyphenPair(leftStem, firstWord)) return null

  const cleanLeft = leftStem.replace(/^[«"(\[…\s]+/, "")
  const cleanRight = firstWord
    .replace(/^[«"(\[…\s]+/, "")
    .replace(/[.,!?:;…»"'\)\]]+$/g, "")

  if (!cleanLeft || !cleanRight) return null

  return {
    pair: { left: cleanLeft, right: cleanRight },
    lastWord,
    leftStem,
    firstWord,
    restNext: nextLine.slice(firstWord.length).trim(),
    prevLineWithoutLastWord: prevLine.slice(0, prevLine.length - lastWord.length),
  }
}

/**
 * Собирает пары «мягкий слоговой перенос» из уже отрисованных строк.
 * Пример: ["При-", "вет"] -> { left: "При", right: "вет" }.
 * Истинные дефисные слова ("Макима-сан", "кто-то", "точь-в-точь") пропускаются.
 */
export function collectSoftHyphenPairs(lines: string[]): SoftHyphenPair[] {
  const pairs: SoftHyphenPair[] = []

  for (let i = 0; i < lines.length - 1; i++) {
    const info = parseSoftHyphenBreak(lines[i], lines[i + 1])
    if (info) pairs.push(info.pair)
  }

  return pairs
}

/**
 * Склеивает обратно мягко перенесённое слово, если пользователь убрал
 * перенос строки и теперь части стоят рядом внутри одной строки:
 * "При- вет" / "При-вет" -> "Привет".
 *
 * Вторая половина слова могла быть отредактирована ("При-ветик"), поэтому
 * проверяем не точное совпадение `pair.right`, а произвольный хвост слова,
 * и склеиваем только если это не настоящее двусоставное слово.
 */
export function normalizeSoftHyphensInLine(line: string, pairs: SoftHyphenPair[]): string {
  let result = line

  for (const pair of pairs) {
    const left = escapeRegExp(pair.left)
    const re = new RegExp(`(^|[\\s(«"\\[…])(${left})-\\s*([а-яА-ЯёЁa-zA-Z0-9]+)`, "gi")
    result = result.replace(re, (match, prefix: string, tailLeft: string, tailRight: string) => {
      if (isCompoundHyphenPair(tailLeft, tailRight)) return match
      return `${prefix}${tailLeft}${tailRight}`
    })
  }

  return result
}

/**
 * Обрабатывает мягкие слоговые переносы на стыке строк.
 *
 * - Если строка заканчивается на `pair.left + "-"`, а следующая начинается
 *   с буквенного продолжения (и это не двусоставное слово), части одного
 *   слова склеиваются в строке `i` без дефиса и без пробела.
 *   Это работает и в авто-, и в ручном режиме: мягкий дефис авто-вёрстки
 *   никогда не должен остаться жёстким символом `-` в `box.rusText`.
 * - Если продолжения нет, «висячий» дефис от старой вёрстки снимается.
 */
export function normalizeCrossLineSoftHyphens(lines: string[], pairs: SoftHyphenPair[]): string[] {
  const result = [...lines]
  if (pairs.length === 0) return result

  const stems = Array.from(new Set(pairs.map((pair) => pair.left)))
  const continuationRe = /^[0-9A-Za-zА-Яа-яЁё]/

  for (let i = 0; i < result.length; i++) {
    const line = result[i]
    const nextLine = result[i + 1] || ""

    const matchedStem = stems.find((stem) => {
      const leftRe = new RegExp(`(^|[\\s(«"\\[…])${escapeRegExp(stem)}-$`, "i")
      return leftRe.test(line)
    })
    if (!matchedStem) continue

    // Срезаем возможные открывающие кавычки/скобки, чтобы понять, с чего
    // начинается продолжение слова в следующей строке.
    const continuation = nextLine.replace(/^[\s(«"\[…]*/, "")
    if (!continuationRe.test(continuation)) {
      result[i] = line.replace(/-$/, "")
      continue
    }

    const firstWord = continuation.split(/\s+/)[0] || ""
    if (isCompoundHyphenPair(matchedStem, firstWord)) continue

    // Склеиваем разорванное слово: "Подож-" + "дите" -> "Подождите".
    result[i] = line.replace(/-$/, "") + continuation
    result.splice(i + 1, 1)
    i--
  }

  return result
}

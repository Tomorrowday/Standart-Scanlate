// manga_ui/lib/typeset/layout/segment-breaker.ts
// Разбиение текстового сегмента на строки: динамическое программирование и жадный фоллбэк

import { cleanLeadingPunct, getWordHyphenSplits, appendHyphenSafe } from "../hyphenation"
import { cleanAndTrimLines, expandOversizedTokens, tokenizeMangaPhrase } from "./tokenizer"
import { scoreMangaLinesConfiguration } from "./line-scoring"
import { registerLayoutCacheClearer } from "./fonts-epoch"

// Кэш замеров ширины текста: подбор кегля пересчитывает те же кандидаты
// строк десятки раз (разные кегли/одинаковые подстроки). Ключ включает
// текущий ctx.font, поэтому кегль, шрифт и начертание учитываются.
const MEASURE_CACHE_LIMIT = 8000
const measureCache = new Map<string, number>()

// Шрифт догрузился — старые ширины fallback-шрифта больше не актуальны
// (иначе Preview получает неверные переносы, а Export — неверный кегль).
registerLayoutCacheClearer(() => measureCache.clear())

function measureCached(ctx: CanvasRenderingContext2D, text: string): number {
  const key = `${ctx.font}\u0000${text}`
  const cached = measureCache.get(key)
  if (cached !== undefined) return cached

  const width = ctx.measureText(text).width
  if (measureCache.size >= MEASURE_CACHE_LIMIT) measureCache.clear()
  measureCache.set(key, width)
  return width
}

export function layoutSegmentOptimal(
  ctx: CanvasRenderingContext2D,
  segmentText: string,
  targetMaxW: number,
  minHyphens: boolean,
  getAllowedW: (lineIdx: number, totalLines: number) => number
): { lines: string[]; hadHyphenation: boolean; hadForcedCharSplit: boolean } {
  const { tokens: initialTokens, joinWithoutSpaceAfter: initialJoins } = tokenizeMangaPhrase(segmentText)
  if (initialTokens.length === 0) {
    return { lines: [], hadHyphenation: false, hadForcedCharSplit: false }
  }

  const { units, isSoftHyphen, joinWithoutSpaceAfter, hadHyphenation, hadForcedCharSplit } =
    expandOversizedTokens(ctx, initialTokens, targetMaxW, minHyphens, initialJoins)

  const m = units.length
  if (m === 1) {
    return { lines: [units[0]], hadHyphenation, hadForcedCharSplit }
  }

  const lineStr: string[][] = Array.from({ length: m }, () => Array(m).fill(""))
  const lineW: number[][] = Array.from({ length: m }, () => Array(m).fill(0))

  for (let i = 0; i < m; i++) {
    let cur = ""
    for (let j = i; j < m; j++) {
      if (j === i) {
        cur = units[j]
      } else {
        // Склеиваем без пробела только там, где токенизатор явно пометил
        // продолжение слова (родной дефис), а не любой пользовательский «-».
        const prevJoinsWithoutSpace = joinWithoutSpaceAfter[j - 1]
        cur = prevJoinsWithoutSpace ? `${cur}${units[j]}` : `${cur} ${units[j]}`
      }
      lineStr[i][j] = cur
      lineW[i][j] = measureCached(ctx, cur)
    }
  }

  // Префиксные суммы мягких переносов: вместо внутреннего цикла по t
  // проверяем «есть ли мягкий перенос в (i, j-1)» за O(1).
  const softPrefix = new Array<number>(m + 1).fill(0)
  for (let t = 0; t < m; t++) {
    softPrefix[t + 1] = softPrefix[t] + (isSoftHyphen[t] ? 1 : 0)
  }

  const totalTextW = lineW[0][m - 1]
  const minLines = Math.max(1, Math.ceil(totalTextW / targetMaxW))
  const maxLines = Math.min(m, Math.max(minLines + 3, Math.ceil(totalTextW / (targetMaxW * 0.52)) + 1))

  let bestLines: string[] | null = null
  let bestScore = Infinity

  for (let k = minLines; k <= maxLines; k++) {
    const dp: number[][] = Array.from({ length: k + 1 }, () => Array(m + 1).fill(Infinity))
    const parent: number[][] = Array.from({ length: k + 1 }, () => Array(m + 1).fill(-1))
    dp[0][0] = 0

    for (let lineIdx = 1; lineIdx <= k; lineIdx++) {
      const allowedForThisLine = getAllowedW(lineIdx - 1, k)

      for (let j = lineIdx; j <= m - (k - lineIdx); j++) {
        for (let i = lineIdx - 1; i < j; i++) {
          if (dp[lineIdx - 1][i] === Infinity) continue

          // Запрещаем внутри одной строки только искусственные мягкие слоговые переносы
          if (softPrefix[j - 1] - softPrefix[i] > 0) continue

          const w = lineW[i][j - 1]
          if (w > allowedForThisLine * 1.01 && j - i > 1) continue

          let stepCost = 0
          if (w > allowedForThisLine) {
            stepCost += (w - allowedForThisLine) * 5000
          }

          const mid = (k - 1) / 2
          const distFromCenter = mid > 0 ? Math.abs(lineIdx - 1 - mid) / mid : 0
          const targetFill = allowedForThisLine * (0.88 - distFromCenter * 0.14)
          const fillDiff = (w - targetFill) / targetMaxW
          stepCost += fillDiff * fillDiff * 100

          const cand = dp[lineIdx - 1][i] + stepCost
          if (cand < dp[lineIdx][j]) {
            dp[lineIdx][j] = cand
            parent[lineIdx][j] = i
          }
        }
      }
    }

    if (dp[k][m] < Infinity) {
      const candidateLines: string[] = []
      let curToken = m
      for (let lineIdx = k; lineIdx >= 1; lineIdx--) {
        const prevToken = parent[lineIdx][curToken]
        if (prevToken === -1) break
        candidateLines.unshift(lineStr[prevToken][curToken - 1])
        curToken = prevToken
      }

      if (candidateLines.length === k) {
        const fullScore = scoreMangaLinesConfiguration(ctx, candidateLines, getAllowedW, targetMaxW)
        if (fullScore < bestScore) {
          bestScore = fullScore
          bestLines = candidateLines
        }
      }
    }
  }

  if (!bestLines || bestScore >= 1e9) {
    const greedyLines = greedyFallbackWithHyphens(
      ctx,
      initialTokens,
      minHyphens,
      (idx) => getAllowedW(idx, Math.max(minLines, 3)),
      initialJoins
    )
    return {
      lines: cleanAndTrimLines(greedyLines.lines),
      hadHyphenation: hadHyphenation || greedyLines.hadHyphenation,
      hadForcedCharSplit: hadForcedCharSplit || greedyLines.hadForcedCharSplit,
    }
  }

  return {
    lines: cleanAndTrimLines(bestLines),
    hadHyphenation,
    hadForcedCharSplit,
  }
}

export function greedyFallbackWithHyphens(
  ctx: CanvasRenderingContext2D,
  tokens: string[],
  minHyphens: boolean,
  getAllowedW: (lineIdx: number) => number,
  joinFlags?: boolean[]
): { lines: string[]; hadHyphenation: boolean; hadForcedCharSplit: boolean } {
  const lines: string[] = []
  let hadHyphenation = false
  let hadForcedCharSplit = false
  const remaining = [...tokens]
  // Флаг «следующий токен без пробела» синхронно с remaining.
  const remainingJoins = tokens.map((_, i) => Boolean(joinFlags?.[i]))
  let curLine = ""
  let curLineJoinsNext = false

  while (remaining.length > 0 && lines.length < 35) {
    const allowedW = getAllowedW(lines.length)
    const w = remaining[0]
    if (!w) {
      remaining.shift()
      remainingJoins.shift()
      continue
    }

    const testLine = curLine
      ? curLineJoinsNext
        ? `${curLine}${w}`.trim()
        : `${curLine} ${w}`.trim()
      : w.trim()

    if (ctx.measureText(testLine).width <= allowedW) {
      curLine = testLine
      curLineJoinsNext = remainingJoins[0]
      remaining.shift()
      remainingJoins.shift()
      continue
    }

    if (minHyphens && curLine.length > 0) {
      lines.push(curLine.trim())
      curLine = ""
      curLineJoinsNext = false
      continue
    }

    if (w.includes(" ")) {
      const parts = w.split(/\s+/)
      const removedJoin = remainingJoins.shift()
      remaining.shift()
      remaining.unshift(...parts)
      remainingJoins.unshift(
        ...parts.map((_, i) => (i === parts.length - 1 ? Boolean(removedJoin) : false))
      )
      continue
    }

    let hyphenated = false
    const splits = getWordHyphenSplits(w)
    for (const split of splits) {
      const hyphenTest = curLine
        ? curLineJoinsNext
          ? `${curLine}${split.prefix}`.trim()
          : `${curLine} ${split.prefix}`.trim()
        : split.prefix.trim()

      if (ctx.measureText(hyphenTest).width <= allowedW) {
        lines.push(hyphenTest.trim())
        curLine = ""
        curLineJoinsNext = false
        remaining[0] = cleanLeadingPunct(split.suffix)
        hyphenated = true
        if (!split.isNativeHyphen) hadHyphenation = true
        break
      }
    }

    if (hyphenated) continue

    if (curLine) {
      lines.push(curLine.trim())
      curLine = ""
      curLineJoinsNext = false
    } else {
      let splitIdx = -1
      let part = ""
      for (let cIdx = 0; cIdx < w.length; cIdx++) {
        const char = w[cIdx]
        const test = appendHyphenSafe(part + char)
        if (ctx.measureText(test).width > allowedW && part.length >= 2) {
          splitIdx = cIdx
          break
        }
        part += char
      }

      hadHyphenation = true
      hadForcedCharSplit = true
      if (splitIdx !== -1) {
        lines.push(appendHyphenSafe(part).trim())
        curLine = ""
        remaining[0] = cleanLeadingPunct(w.slice(splitIdx))
      } else {
        lines.push(w.trim())
        curLine = ""
        remaining.shift()
      }
    }
  }

  if (curLine) {
    lines.push(curLine.trim())
  }

  return { lines, hadHyphenation, hadForcedCharSplit }
}

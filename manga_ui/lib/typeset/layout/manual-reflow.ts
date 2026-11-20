// manga_ui/lib/typeset/layout/manual-reflow.ts
// Сохранение ручных переносов строк, расставленных пользователем

import { joinLinesRemovingSoftHyphens } from "./compound-words"
import {
  collectSoftHyphenPairs,
  normalizeCrossLineSoftHyphens,
  normalizeSoftHyphensInLine,
} from "./soft-hyphen-normalizer"

/**
 * Невидимый маркер (Word Joiner) в конце текста означает, что пользователь
 * принудительно зафиксировал одну строку: движок не должен разбивать её
 * автоматически, а обязан уменьшать кегль, пока строка не влезет целиком.
 *
 * ВАЖНО: маркер хранится только в `box.rusText` и НИКОГДА не попадает
 * в `<textarea>` (ни в renderedLines, ни в editableLines).
 */
export const FORCED_SINGLE_LINE_MARKER = "\u2060"

export interface ReflowOptions {
  /**
   * Был ли блок ручным до начала правки: в `box.rusText` уже были `\n`
   * или маркер принудительной однострочности.
   */
  wasManualBeforeEdit?: boolean
  /**
   * Менял ли пользователь структуру строк во время этой сессии правки
   * (нажимал Enter или удалял перенос строки через Backspace/Delete).
   */
  hasUserModifiedLineBreaks?: boolean
  /**
   * Был ли у блока маркер `FORCED_SINGLE_LINE_MARKER` до начала правки.
   * Нужен, чтобы восстановить однострочный режим, даже если рендер дал 1 строку.
   */
  hadForcedSingleLine?: boolean
}

/** Количество слов в каждой строке — устойчивый отпечаток ручной разбивки. */
export function getLineWordCounts(lines: string[]): number[] {
  return lines.map((l) => l.trim().split(/\s+/).filter(Boolean).length)
}

/**
 * Определяет, менял ли пользователь структуру строк.
 *
 * Недостаточно сравнивать только число строк: перенос слова на соседнюю
 * строку (`"Привет как\nдела"` → `"Привет\nкак дела"`) сохраняет их количество,
 * но это уже ручная разбивка. Сравниваем распределение слов по строкам.
 *
 * `prevLineCount` — число строк на предыдущем onChange, `hadBreakEdit` —
 * был ли Enter/Backspace по переносам в этой сессии. Если пользователь нажал
 * Enter и сразу Backspace в том же месте, распределение слов совпадёт
 * со снапшотом — блок возвращается в авто-режим.
 */
export function hasModifiedLineBreaks(
  snapshotLines: string[],
  editedValue: string,
  prevLineCount: number,
  hadBreakEdit: boolean
): boolean {
  const nextLines = editedValue.split(/\r?\n/)
  const hadEdit = hadBreakEdit || nextLines.length !== prevLineCount

  if (nextLines.length !== snapshotLines.length) return true
  if (!hadEdit) return false

  const nextCounts = getLineWordCounts(nextLines)
  const snapshotCounts = getLineWordCounts(snapshotLines)
  if (nextCounts.length !== snapshotCounts.length) return true
  return nextCounts.some((count, idx) => count !== snapshotCounts[idx])
}

/** Есть ли в тексте ручные переносы строк или маркер принудительной однострочности. */
export function hasManualLineBreaks(text: string | null | undefined): boolean {
  if (!text) return false
  return /\r?\n/.test(text) || text.includes(FORCED_SINGLE_LINE_MARKER)
}

/** Убирает невидимый маркер однострочности — для текста, попадающего в textarea. */
export function stripForcedSingleLineMarker(text: string | null | undefined): string {
  return (text || "").split(FORCED_SINGLE_LINE_MARKER).join("")
}

/**
 * Вычисляет сохраняемый текст `box.rusText` после правки в textarea.
 *
 * Главное правило: авто-бабл должен остаться авто-баблом, если пользователь
 * не менял структуру строк. Исправление опечатки или дописывание слова
 * склеивает строки обратно в один поток (`joinLinesRemovingSoftHyphens`),
 * чтобы движок сам красиво перебалансировал текст.
 *
 * Ручные `\n` фиксируются только если блок был ручным до правки или
 * пользователь нажал Enter / удалил перенос строки.
 *
 * `editedText` всегда приходит из `<textarea>` и не содержит невидимого маркера;
 * маркер однострочности добавляется только в возвращаемый storage-текст.
 */
export function reflowFromManualLines(
  previousRenderedLines: string[],
  editedText: string,
  options: boolean | ReflowOptions = true
): string {
  const opts: ReflowOptions = typeof options === "boolean" ? { wasManualBeforeEdit: options } : options
  const wasManualBeforeEdit = opts.wasManualBeforeEdit ?? true
  const hasUserModifiedLineBreaks = opts.hasUserModifiedLineBreaks ?? false
  const hadForcedSingleLine = opts.hadForcedSingleLine ?? false

  // На случай, если маркер всё же оказался во входном тексте (старый код/undo).
  const hadExplicitMarker = editedText.includes(FORCED_SINGLE_LINE_MARKER)
  const withoutMarker = editedText.split(FORCED_SINGLE_LINE_MARKER).join("")

  const rawEditedLines = withoutMarker
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)

  if (rawEditedLines.length === 0) return ""

  const softPairs = collectSoftHyphenPairs(previousRenderedLines)
  const normalizedLines = normalizeCrossLineSoftHyphens(
    rawEditedLines
      .map((line) => normalizeSoftHyphensInLine(line, softPairs).trim())
      .filter(Boolean),
    softPairs
  )

  if (normalizedLines.length === 0) return ""

  const isManualLayout = wasManualBeforeEdit || hasUserModifiedLineBreaks

  // Авто-режим: пользователь не трогал разбивку строк — отдаём текст одним
  // потоком, чтобы авто-движок заново разложил его ромбом.
  if (!isManualLayout) {
    return joinLinesRemovingSoftHyphens(normalizedLines)
  }

  const forceSingleLine =
    normalizedLines.length === 1 &&
    (hadExplicitMarker || hadForcedSingleLine || previousRenderedLines.length > 1)

  return normalizedLines.join("\n") + (forceSingleLine ? FORCED_SINGLE_LINE_MARKER : "")
}

/**
 * Проецирует строки, посчитанные по UPPERCASE-тексту, обратно на исходный
 * регистр. Идём по символам отрисованной строки и синхронно вычитываем
 * соответствующие символы из исходного текста. Вставленные движком мягкие
 * дефисы сохраняются, чтобы ручная правка могла их корректно снять.
 */
export function projectLinesToOriginalCase(rawText: string, renderedLines: string[]): string[] | null {
  let pos = 0
  const out: string[] = []

  const skipWhitespace = () => {
    while (pos < rawText.length && /\s/.test(rawText[pos])) pos++
  }

  for (const renderedLine of renderedLines) {
    let lineOut = ""
    let pendingSpace = false

    for (let i = 0; i < renderedLine.length; i++) {
      const ch = renderedLine[i]

      if (/\s/.test(ch)) {
        if (lineOut.length > 0) pendingSpace = true
        continue
      }

      skipWhitespace()

      if (pendingSpace) {
        lineOut += " "
        pendingSpace = false
      }

      if (ch === "-" && rawText[pos] !== "-") {
        // Мягкий слоговой перенос, которого нет в исходном тексте
        lineOut += "-"
        continue
      }

      if (pos >= rawText.length) return null

      const rawCh = rawText[pos]
      if (rawCh.toLowerCase() !== ch.toLowerCase()) return null

      lineOut += rawCh
      pos++
    }

    out.push(lineOut)
  }

  skipWhitespace()
  if (pos < rawText.length) return null

  return out
}

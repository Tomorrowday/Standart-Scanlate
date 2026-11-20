// manga_ui/lib/typeset/layout.ts
/**
 * Автоперенос строк, подбор кегля под геометрию бабла и оптическое центрирование.
 * Движок верстки разложен по модулям в manga_ui/lib/typeset/layout/:
 *
 *   ellipse-geometry.ts    — getEllipseWidthAtY
 *   compound-words.ts      — isCompoundHyphenPair, joinLinesRemovingSoftHyphens
 *   tokenizer.ts           — NON_BREAKING_PREPOSITIONS, ATTACH_TO_PREV_WORDS,
 *                            cleanAndTrimLines, tokenizeMangaPhrase, expandOversizedTokens
 *   line-scoring.ts        — scoreMangaLinesConfiguration
 *   segment-breaker.ts     — layoutSegmentOptimal, greedyFallbackWithHyphens
 *   manual-reflow.ts       — reflowFromManualLines, hasManualLineBreaks,
 *                            stripForcedSingleLineMarker, FORCED_SINGLE_LINE_MARKER
 *   bubble-layout-engine.ts — layoutBubbleTextLines
 */

export interface BubbleLayoutResult {
  lines: string[]
  actualFontSize: number
  lineHeight: number
}

export * from "./layout/ellipse-geometry"
export * from "./layout/compound-words"
export * from "./layout/tokenizer"
export * from "./layout/line-scoring"
export * from "./layout/segment-breaker"
export * from "./layout/manual-reflow"
export * from "./layout/bubble-layout-engine"
export * from "./layout/bubble-display-lines"
export * from "./layout/fonts-epoch"

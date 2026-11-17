// manga_ui/lib/api/dictionary.ts
/**
 * API-запросы к локальному японско-русскому словарю (Warodai + JMdict + GiNZA/Sudachi + Глоссарий).
 * - клиентский кэш успешных разборов
 * - дедупликация одновременных запросов (in-flight map) между сканом и правой панелью
 * - очередь параллельности (не более 4 одновременных запросов к бэкенду) + retry
 */

import { API_BASE_URL, handleApiResponse } from "./client"

export interface DictSense {
  source: "warodai" | "jmdict_ru" | "jmdict_en" | "jmnedict" | string
  kanji: string
  reading: string
  pos: string
  meanings: string[]
}

export interface GlossaryHit {
  id: number
  jap_word: string
  rus_word: string
  context: string
}

export interface TokenSpan {
  surface: string
  lemma: string
  reading: string
  pos_ru: string
  inflection_chain: string[]
  is_punct_or_particle: boolean
  ner_label?: string | null
  glossary_match?: GlossaryHit | null
  dict_entries: DictSense[]
}

export interface DictStatusResponse {
  success: boolean
  db_path: string
  total_entries: number
  sources: Record<string, number>
  is_full_dictionary_loaded: boolean
  local_zip_files: string[]
  build_progress: {
    is_building: boolean
    stage: string
    message: string
    error?: string | null
  }
  nlp?: {
    active_backend: string
    has_ahocorasick: boolean
    loaded_ginza_models: string[]
  }
}

export const DICT_GLOSSARY_UPDATED_EVENT = "manga-dict-glossary-updated"

// Кэш успешных токенизированных фраз: ключ `${titleId || 0}:${nlpMode}:${japText}`
const analyzeCache = new Map<string, TokenSpan[]>()

// Карта текущих выполняющихся запросов (чтобы скан и правая карточка не дублировали POST)
const inFlightAnalyze = new Map<string, Promise<TokenSpan[]>>()

// Ограничитель параллельных запросов к /api/dictionary/analyze (макс. 4 одновременно)
const MAX_CONCURRENT_ANALYZE = 4
let activeAnalyzeCount = 0
const waitQueue: Array<() => void> = []

function acquireSlot(): Promise<void> {
  if (activeAnalyzeCount < MAX_CONCURRENT_ANALYZE) {
    activeAnalyzeCount++
    return Promise.resolve()
  }
  return new Promise<void>((resolve) => {
    waitQueue.push(() => {
      activeAnalyzeCount++
      resolve()
    })
  })
}

function releaseSlot(): void {
  activeAnalyzeCount = Math.max(0, activeAnalyzeCount - 1)
  const next = waitQueue.shift()
  if (next) next()
}

export function clearDictionaryAnalyzeCache() {
  analyzeCache.clear()
  inFlightAnalyze.clear()
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(DICT_GLOSSARY_UPDATED_EVENT))
  }
}

async function fetchAnalyzeWithRetry(
  trimmed: string,
  titleId?: number | null,
  nlpMode: string = "auto",
  retries: number = 2
): Promise<{ tokens: TokenSpan[]; isBuilding: boolean }> {
  await acquireSlot()
  try {
    let lastError: unknown = null
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const res = await fetch(`${API_BASE_URL}/api/dictionary/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title_id: titleId ?? null,
            jap_text: trimmed,
            nlp_mode: nlpMode,
          }),
        })
        const data = await handleApiResponse<{
          success: boolean
          tokens: TokenSpan[]
          is_building?: boolean
        }>(res, "Ошибка морфологического разбора бабла")
        return {
          tokens: data.tokens || [],
          isBuilding: Boolean(data.is_building),
        }
      } catch (err) {
        lastError = err
        if (attempt < retries) {
          await new Promise((r) => setTimeout(r, 250 * (attempt + 1)))
        }
      }
    }
    throw lastError
  } finally {
    releaseSlot()
  }
}

export async function analyzeBubbleJapText(
  japText: string,
  titleId?: number | null,
  nlpMode: string = "auto",
  skipCache: boolean = false
): Promise<TokenSpan[]> {
  const trimmed = (japText || "").trim()
  if (!trimmed) return []

  const cacheKey = `${titleId || 0}:${nlpMode}:${trimmed}`
  if (!skipCache && analyzeCache.has(cacheKey)) {
    return analyzeCache.get(cacheKey)!
  }

  if (!skipCache && inFlightAnalyze.has(cacheKey)) {
    return inFlightAnalyze.get(cacheKey)!
  }

  const requestPromise = (async (): Promise<TokenSpan[]> => {
    try {
      const { tokens, isBuilding } = await fetchAnalyzeWithRetry(trimmed, titleId, nlpMode, 2)

      // Кэшируем только осмысленный результат и только когда не идёт фоновая сборка словаря
      if (tokens.length > 0 && !isBuilding) {
        if (analyzeCache.size > 600) {
          analyzeCache.clear()
        }
        analyzeCache.set(cacheKey, tokens)
      }
      return tokens
    } catch {
      // НЕ кэшируем аварийный фоллбэк, чтобы при следующем рендере/ховере запрос повторился
      return [
        {
          surface: trimmed,
          lemma: trimmed,
          reading: "",
          pos_ru: "Текст",
          inflection_chain: [],
          is_punct_or_particle: false,
          dict_entries: [],
        },
      ]
    } finally {
      inFlightAnalyze.delete(cacheKey)
    }
  })()

  inFlightAnalyze.set(cacheKey, requestPromise)
  return requestPromise
}

export async function lookupDictionaryWord(
  query: string,
  titleId?: number | null
): Promise<{ lemma: string; chain: string[]; entries: DictSense[] }> {
  const res = await fetch(`${API_BASE_URL}/api/dictionary/lookup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title_id: titleId ?? null,
      query: query.trim(),
    }),
  })
  return handleApiResponse(res, "Ошибка поиска слова в словаре")
}

export async function upsertGlossaryFromDictionary(params: {
  title_id: number
  jap_word: string
  rus_word: string
  context?: string
}): Promise<GlossaryHit> {
  const res = await fetch(`${API_BASE_URL}/api/dictionary/glossary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  })
  const data = await handleApiResponse<{ success: boolean; item: GlossaryHit }>(
    res,
    "Ошибка сохранения термина в глоссарий"
  )
  clearDictionaryAnalyzeCache()
  return data.item
}

export async function getDictionaryStatus(): Promise<DictStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/api/dictionary/status`)
  return handleApiResponse(res, "Ошибка получения статуса словаря")
}

export async function triggerDictionaryBuild(forceRebuild: boolean = false): Promise<{
  success: boolean
  imported?: Record<string, number>
  error?: string
  status: DictStatusResponse
}> {
  const res = await fetch(`${API_BASE_URL}/api/dictionary/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force_rebuild: forceRebuild }),
  })
  const data = await handleApiResponse<any>(res, "Ошибка сборки словаря")
  clearDictionaryAnalyzeCache()
  return data
}

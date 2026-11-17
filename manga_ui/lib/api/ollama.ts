// manga_ui/lib/api/ollama.ts
/**
 * Клиент локальной нейросети Ollama (проверка соединения, выбор текстовой модели и пакетный перевод
 * с учётом типа бабла, синопсиса и глоссария).
 * Прямое сетевое взаимодействие с локальным сервером Ollama (с передачей типа бабла class_id,
 * синопсиса и глоссария).
 */

export interface OllamaModelInfo {
  name: string
  size: number
  modified_at: string
}

export interface OllamaTranslateItem {
  id: string
  text: string
  speaker?: string
  class_id?: number
}

const CLASS_ID_TO_LABEL: Record<number, string> = {
  0: "bubble",
  1: "thought",
  2: "text",
  3: "sfx",
}

const EMBEDDING_KEYWORDS = ["embed", "nomic-embed", "bge-", "mxbai-embed", "minilm", "snowflake-arctic-embed"]

/**
 * Снимает внешние кавычки только если они обрамляют всю реплику целиком,
 * а не принадлежат двум разным цитатам в начале и в конце.
 */
function stripWrappingQuotes(text: string): string {
  if (text.length < 2) return text

  if (text.startsWith("«") && text.endsWith("»")) {
    let depth = 0
    let closedBeforeEnd = false
    for (let i = 0; i < text.length; i++) {
      if (text[i] === "«") depth++
      else if (text[i] === "»") {
        depth--
        if (depth === 0 && i < text.length - 1) {
          closedBeforeEnd = true
          break
        }
      }
    }
    if (!closedBeforeEnd && depth === 0) return text.slice(1, -1).trim()
  }

  if (text.startsWith('"') && text.endsWith('"')) {
    if (text.slice(1, -1).indexOf('"') === -1) return text.slice(1, -1).trim()
  }

  return text
}

export function pickBestOllamaModel(models: string[]): string {
  if (!models || models.length === 0) return "qwen2.5:7b"
  const chatModels = models.filter(
    (m) => !EMBEDDING_KEYWORDS.some((kw) => m.toLowerCase().includes(kw))
  )
  const pool = chatModels.length > 0 ? chatModels : models
  return (
    pool.find((m) => {
      const low = m.toLowerCase()
      return low.includes("qwen") || low.includes("llama") || low.includes("gemma") || low.includes("mistral")
    }) || pool[0]
  )
}

export async function checkOllamaConnection(baseUrl: string = "http://localhost:11434"): Promise<{ ok: boolean; models: string[] }> {
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 2000)

    const res = await fetch(`${baseUrl}/api/tags`, {
      method: "GET",
      signal: controller.signal,
    })
    clearTimeout(timer)

    if (!res.ok) return { ok: false, models: [] }
    const data = await res.json()
    const models = (data.models || []).map((m: any) => m.name)
    return { ok: true, models }
  } catch {
    return { ok: false, models: [] }
  }
}

export async function runOllamaBatchTranslate(
  items: OllamaTranslateItem[],
  options: {
    baseUrl?: string
    model?: string
    synopsis?: string
    glossary?: Array<{ jap?: string; rus: string; context?: string }>
  } = {}
): Promise<Record<string, string>> {
  if (items.length === 0) return {}

  const baseUrl = options.baseUrl || "http://localhost:11434"
  const model = options.model || "qwen2.5:7b"

  const lines = items.map((it, idx) => {
    const typeLabel = CLASS_ID_TO_LABEL[it.class_id ?? 0] || "bubble"
    const spk = it.speaker ? `[${it.speaker}]: ` : ""
    return `[${idx + 1}] (${typeLabel}) ${spk}${it.text}`
  })

  const synopsisBlock =
    options.synopsis && options.synopsis.trim()
      ? `\nСИНОПСИС И СТИЛЬ ТАЙТЛА:\n${options.synopsis.trim()}\n`
      : ""

  let glossaryBlock = ""
  if (options.glossary && options.glossary.length > 0) {
    const gLines = options.glossary.map((g) => {
      const jp = g.jap?.trim() ? `${g.jap.trim()} -> ` : ""
      const ctx = g.context?.trim() ? ` (${g.context.trim()})` : ""
      return `- ${jp}${g.rus.trim()}${ctx}`
    })
    glossaryBlock = `\nОБЯЗАТЕЛЬНЫЙ ГЛОССАРИЙ И ПЕРСОНАЖИ:\n${gLines.join("\n")}\n`
  }

  const prompt = `Ты профессиональный литературный переводчик манги с японского на русский язык.
Переведи следующие реплики манги по порядку.
В круглых скобках указан тип блока:
- (bubble) — живая разговорная речь персонажа
- (thought) — внутренний монолог / мысли / закадровый текст
- (text) — лаконичная надпись на фоне или приписка от руки
- (sfx) — звуковой эффект (ономатопея)
${synopsisBlock}${glossaryBlock}
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать в ответе тип блока, имена спикеров, префиксы или пояснения!
Формат ответа СТРОГО:
[1] Русский текст первой реплики
[2] Русский текст второй реплики

Оригинал:
${lines.join("\n")}`

  const response = await fetch(`${baseUrl}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: model,
      prompt: prompt,
      stream: false,
      options: {
        temperature: 0.3,
      },
    }),
  })

  if (!response.ok) {
    throw new Error(`Ошибка Ollama (${response.statusText}). Убедитесь, что модель ${model} загружена.`)
  }

  const data = await response.json()
  const rawText: string = data.response || ""

  const result: Record<string, string> = {}
  const blocks: Record<number, string[]> = {}
  const order: number[] = []
  let currentIdx = -1

  for (const rawLine of rawText.split("\n")) {
    const line = rawLine.trim()
    if (!line || line.startsWith("```")) continue

    const match = line.match(/^\[(\d+)\]\s*(.*)$/)
    if (match) {
      currentIdx = parseInt(match[1], 10) - 1
      if (!(currentIdx in blocks)) {
        blocks[currentIdx] = []
        order.push(currentIdx)
      }
      blocks[currentIdx].push(match[2])
    } else if (currentIdx >= 0) {
      // Продолжение многострочного перевода предыдущей реплики
      blocks[currentIdx].push(line)
    }
  }

  for (const idx of order) {
    if (idx >= 0 && idx < items.length) {
      let clean = blocks[idx].join("\n").trim()
      clean = clean.replace(/^\((?:bubble|thought|text|sfx)\)\s*:?\s*/i, "")
      clean = clean.replace(/^\[[^\]]+\]\s*:?\s*/, "")
      clean = stripWrappingQuotes(clean)
      result[items[idx].id] = clean
    }
  }

  return result
}

// manga_ui/lib/api/ollama.ts
/**
 * Клиент локальной Ollama для UI: проверка соединения и выбор модели.
 *
 * Сам перевод выполняется на бэкенде (`POST /api/translate/batch` →
 * services/translator_ops/ollama.py), чтобы страница и глава использовали
 * один промпт, один парсер и одинаковые чанки.
 */

import { API_BASE_URL, handleApiResponse } from "./client"

const EMBEDDING_KEYWORDS = ["embed", "nomic-embed", "bge-", "mxbai-embed", "minilm", "snowflake-arctic-embed"]

/** Выбирает чат-модель, игнорируя embedding/rerank-модели. */
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

/**
 * Проверка Ollama через бэкенд: браузер не стучится напрямую в :11434,
 * поэтому LAN-адрес и CORS Ollama больше не ломают UI.
 */
export async function checkOllamaConnection(): Promise<{ ok: boolean; models: string[] }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/ollama/status`)
    const data = await handleApiResponse<{ ok: boolean; models: string[] }>(
      res,
      "Ошибка проверки Ollama"
    )
    return { ok: Boolean(data.ok), models: data.models || [] }
  } catch {
    return { ok: false, models: [] }
  }
}

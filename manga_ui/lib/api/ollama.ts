// manga_ui/lib/api/ollama.ts
/**
 * Контракт клиента локальной нейросети Ollama (проверка соединения, выбор текстовой модели и пакетный перевод с учётом типа бабла, синопсиса и глоссария).
 * Реализация: manga_ui/lib/api/ollama_impl.ts
 * Зависимости реализации: fetch, AbortController, регулярные выражения парсинга ответов
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

export {
  checkOllamaConnection,
  pickBestOllamaModel,
  runOllamaBatchTranslate,
} from "./ollama_impl"

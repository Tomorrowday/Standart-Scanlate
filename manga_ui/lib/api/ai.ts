// manga_ui/lib/api/ai.ts
/**
 * API-запросы к модулям распознавания OCR и перевода текста.
 * Выполнение сетевых запросов MangaOCR и Gemini API.
 *
 * runOcr(pageId, x, y, width, height, rotation?, blockId?, classId?)
 *   blockId — id блока в БД (чтобы бэкенд точно знал, какой блок распознаётся,
 *             даже если рамку подвинули вручную и ещё не сохранили);
 *   classId — класс блока (0..3), передаётся в OCR напрямую.
 */

import { API_BASE_URL, handleApiResponse } from "./client"

export async function runOcr(
  pageId: number,
  x: number,
  y: number,
  width: number,
  height: number,
  rotation: number = 0,
  blockId?: string,
  classId?: number
): Promise<string> {
  // Ошибка пробрасывается наверх: вызывающий код не должен записывать
  // заглушку «❌ Ошибка» в japText и в БД.
  const response = await fetch(`${API_BASE_URL}/api/ocr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page_id: pageId,
      x,
      y,
      width,
      height,
      rotation,
      block_id: blockId,
      class_id: classId,
    }),
  })
  const data = await handleApiResponse<{ success: boolean; text?: string; error?: string }>(
    response,
    "Ошибка сервера OCR"
  )
  if (!data.success || data.text === undefined) {
    throw new Error(data.error || "Неизвестная ошибка OCR")
  }
  return data.text
}

export async function runTranslate(
  japText: string,
  context: string = "",
  glossary: Record<string, string> = {},
  titleDescription: string = ""
): Promise<string> {
  if (!japText.trim()) return ""

  // Ошибка пробрасывается наверх: заглушка не должна попадать в rusText/БД.
  const response = await fetch(`${API_BASE_URL}/api/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: japText,
      context,
      glossary,
      title_description: titleDescription,
    }),
  })
  const data = await handleApiResponse<{ success: boolean; translated?: string; error?: string }>(
    response,
    "Ошибка сервера перевода"
  )
  if (!data.success || data.translated === undefined) {
    throw new Error(data.error || "Неизвестная ошибка перевода")
  }
  return data.translated
}

export async function runBatchTranslate(
  items: Array<{ id: string; text: string; speaker?: string; order_index?: number; class_id?: number }>,
  pageId?: number
): Promise<Record<string, string>> {
  if (items.length === 0) return {}

  // Сбой не маскируется пустым объектом: вызывающий код должен узнать об ошибке.
  const response = await fetch(`${API_BASE_URL}/api/translate/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, page_id: pageId }),
  })
  const data = await handleApiResponse<{ success: boolean; translations?: Record<string, string>; error?: string }>(
    response,
    "Ошибка пакетного перевода"
  )
  if (!data.success || !data.translations) {
    throw new Error(data.error || "Ошибка пакетного перевода")
  }
  return data.translations
}

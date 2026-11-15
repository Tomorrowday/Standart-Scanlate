// manga_ui/lib/api/ai.ts
/**
 * Контракт API-запросов к модулям распознавания OCR и перевода текста.
 * Реализация: manga_ui/lib/api/ai_impl.ts
 * Зависимости реализации: manga_ui/lib/api/client (API_BASE_URL, handleApiResponse)
 *
 * runOcr(pageId, x, y, width, height, rotation?, blockId?, classId?)
 *   blockId — id блока в БД (чтобы бэкенд точно знал, какой блок распознаётся,
 *             даже если рамку подвинули вручную и ещё не сохранили);
 *   classId — класс блока (0..3), передаётся в OCR напрямую.
 */

export {
  runOcr,
  runTranslate,
  runBatchTranslate,
} from "./ai_impl"
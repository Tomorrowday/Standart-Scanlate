// manga_ui/lib/api/pages.ts
/**
 * API-запросы операций со страницами манги, баблами, клином и экспортом.
 * Реализация запросов для страниц, баблов, пошагового отката клина и взаимодействия с бэкендом.
 */

import type { PageItem, TextBlock } from "../types"
import { API_BASE_URL, handleApiResponse } from "./client"

/** Payload одного бабла для POST /api/pages/{id}/blocks. */
export interface PageBlockPayload {
  id: string
  class_id?: number
  x: number
  y: number
  width: number
  height: number
  rotation?: number
  jap_text: string
  rus_text: string
  speaker?: string
  order_index?: number
  font_size?: number
  font_family?: string
  is_bold?: boolean
  is_italic?: boolean
  is_uppercase?: boolean
  has_stroke?: boolean
  text_color?: string
  shape?: string
  padding_mode?: string
  min_hyphens?: boolean
  status: string
}

/** Единое преобразование TextBlock → payload (используется обычным и keepalive-сохранением). */
export function toPageBlocksPayload(blocks: TextBlock[]): PageBlockPayload[] {
  return blocks.map((b) => ({
    id: b.id,
    class_id: b.class_id ?? 0,
    x: b.x,
    y: b.y,
    width: b.width,
    height: b.height,
    rotation: b.rotation || 0,
    jap_text: b.japText,
    rus_text: b.rusText,
    speaker: b.speaker || "",
    order_index: b.orderIndex || 0,
    font_size: b.fontSize !== undefined && b.fontSize !== null ? Number(b.fontSize) : undefined,
    font_family: b.fontFamily || "v_CCFaceFront",
    is_bold: Boolean(b.isBold),
    is_italic: Boolean(b.isItalic),
    is_uppercase: Boolean(b.isUppercase),
    has_stroke: Boolean(b.hasStroke),
    text_color: b.textColor || "black",
    shape: b.shape || "rect",
    padding_mode: b.paddingMode || "safe",
    min_hyphens: b.minHyphens !== undefined ? Boolean(b.minHyphens) : true,
    status: b.status,
  }))
}

export function getPageImageUrl(pageId: number): string {
  return `${API_BASE_URL}/api/pages/${pageId}/image`
}

export function getPageCleanImageUrl(pageId: number): string {
  return `${API_BASE_URL}/api/pages/${pageId}/clean-image`
}

export async function releaseVram() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/pages/release-vram`, {
      method: "POST",
    })
    return await handleApiResponse<any>(res, "Ошибка очистки VRAM")
  } catch (error) {
    console.warn("Не удалось очистить VRAM:", error)
  }
}

export async function unloadAllModels(): Promise<{
  success: boolean
  vram_before_mb?: number
  vram_after_mb?: number
  freed_mb?: number
  error?: string
}> {
  const res = await fetch(`${API_BASE_URL}/api/pages/unload-models`, {
    method: "POST",
  })
  return await handleApiResponse(res, "Ошибка выгрузки моделей")
}

export async function getPageDetails(pageId: number, cleanupBackups = true): Promise<PageItem | null> {
  try {
    const query = cleanupBackups ? "" : "?cleanup_backups=false"
    const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}${query}`)
    const data = await res.json()
    return data.success ? data.page : null
  } catch {
    return null
  }
}

export async function getPageSpeakers(pageId: number): Promise<string[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/speakers`)
    const data = await res.json()
    return data.speakers || []
  } catch {
    return []
  }
}

export async function runPageAutoDetect(pageId: number, conf?: number, autoOval?: boolean) {
  const params = new URLSearchParams()
  if (conf !== undefined) params.append("conf", String(conf))
  if (autoOval !== undefined) params.append("auto_oval", String(autoOval))
  const query = params.toString() ? `?${params.toString()}` : ""

  const response = await fetch(`${API_BASE_URL}/api/pages/${pageId}/detect${query}`, {
    method: "POST",
  })
  // Реальный сбой — исключение (architecture-decisions.md §16), а не
  // success: false с HTTP 200: иначе UI помечает упавшую страницу как detected.
  return await handleApiResponse<any>(response, "Ошибка сервера детекции")
}

export async function getPageBlocks(pageId: number) {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/blocks`)
  const data = await handleApiResponse<any>(res, "Ошибка получения баблов")
  if (!data.success) throw new Error(data.error)
  return data.blocks
}

export async function savePageBlocks(pageId: number, blocks: PageBlockPayload[]) {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/blocks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  })
  return await handleApiResponse<any>(res, "Ошибка сохранения баблов")
}

/**
 * Best-effort сохранение при закрытии вкладки через `keepalive`.
 * Браузер ограничивает тело ~64 КБ, поэтому крупные страницы не отправляем
 * (остаётся только предупреждение beforeunload).
 */
export function savePageBlocksKeepalive(pageId: number, blocks: PageBlockPayload[]): void {
  try {
    const body = JSON.stringify({ blocks })
    if (new Blob([body]).size > 64 * 1024) {
      console.warn("Keepalive-сохранение пропущено: payload больше 64 КБ")
      return
    }
    void fetch(`${API_BASE_URL}/api/pages/${pageId}/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch((e) => console.warn("Keepalive-сохранение не удалось:", e))
  } catch (e) {
    console.warn("Keepalive-сохранение не удалось:", e)
  }
}

export async function runCleanPage(pageId: number, mode: "auto" | "lama" | "white" = "auto") {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/clean?mode=${mode}`, {
    method: "POST",
  })
  return await handleApiResponse<any>(res, "Ошибка клина страницы")
}

export async function revertCleanPage(pageId: number) {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/clean`, {
    method: "DELETE",
  })
  return await handleApiResponse<any>(res, "Ошибка отката клина")
}

export async function undoLastCleanStep(pageId: number) {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/undo-clean`, {
    method: "POST",
  })
  return await handleApiResponse<any>(res, "Ошибка отката последнего шага клина")
}

export async function runSpotClean(
  pageId: number,
  rect: { x: number; y: number; width: number; height: number; rotation?: number; shape?: string; class_id?: number },
  method: "auto" | "lama" | "white" | "lama_box" = "auto"
) {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/clean-spot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      rotation: rect.rotation || 0.0,
      shape: rect.shape || "rect",
      class_id: rect.class_id ?? 0,
      method,
    }),
  })
  return await handleApiResponse<any>(res, "Ошибка точечного клина")
}

export async function saveTranslatedPage(pageId: number, imageBlob: Blob) {
  const formData = new FormData()
  formData.append("file", imageBlob, "translated.png")

  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/save-translated`, {
    method: "POST",
    body: formData,
  })
  return await handleApiResponse<any>(res, "Ошибка запекания страницы")
}

export async function openTranslatedFolder(pageId: number) {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/open-folder`, {
    method: "POST",
  })
  return await handleApiResponse<any>(res, "Не удалось открыть папку")
}

/** Bounding box мазка кисти в пикселях оригинального изображения. */
export interface BrushMaskRect {
  x: number
  y: number
  width: number
  height: number
}

export async function runBrushClean(
  pageId: number,
  maskBase64: string,
  mode: "lama" | "white" | "black" = "lama",
  maskRect?: BrushMaskRect
) {
  const res = await fetch(`${API_BASE_URL}/api/pages/${pageId}/clean-brush`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mask_base64: maskBase64,
      mode,
      mask_rect: maskRect,
    }),
  })
  return await handleApiResponse<any>(res, "Ошибка кисти восстановления")
}

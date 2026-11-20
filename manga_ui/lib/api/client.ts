// lib/api/client.ts
// Базовый HTTP-клиент для взаимодействия с локальным FastAPI BFF.
// Ошибки бэкенд отдаёт HTTP-кодами 4xx/5xx (HTTPException); `success: false`
// с HTTP 200 остаётся только для информационных ответов (отмена, пустой список).

export const API_BASE_URL = "http://127.0.0.1:8000"

/** Ошибка API с HTTP-статусом — позволяет различать 404/409/500 на клиенте. */
export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

export async function handleApiResponse<T>(response: Response, defaultErrorMessage: string): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new ApiError(
      errorData.detail || errorData.error || `${defaultErrorMessage}: ${response.statusText}`,
      response.status
    )
  }
  return response.json()
}
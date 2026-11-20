// manga_ui/lib/ui-layer-store.ts
// Лёгкий счётчик открытых модальных окон без Context и лишних ререндеров.
// Пока открыт хотя бы один UI-слой, глобальные хоткеи страницы отключаются.

import { useSyncExternalStore } from "react"

let openLayersCount = 0
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((listener) => listener())
}

/**
 * Регистрирует открытый UI-слой. Возвращает функцию снятия регистрации
 * (её удобно возвращать из useEffect).
 */
export function openUiLayer(): () => void {
  openLayersCount += 1
  emit()
  let released = false
  return () => {
    if (released) return
    released = true
    openLayersCount = Math.max(0, openLayersCount - 1)
    emit()
  }
}

/** true, если открыт хотя бы один модальный слой. */
export function useUiLayerOpen(): boolean {
  return useSyncExternalStore(
    (callback) => {
      listeners.add(callback)
      return () => listeners.delete(callback)
    },
    () => openLayersCount > 0,
    () => false
  )
}

// manga_ui/lib/typeset/layout/fonts-epoch.ts
/**
 * Эпоха загрузки шрифтов для кэшей вёрстки.
 *
 * До загрузки манга-шрифтов `measureText` считает ширины по fallback
 * `sans-serif`, и эти значения попадают в кэши `measureCache` и `cache`.
 * Когда `document.fonts.ready` / `loadingdone` завершается, мы инкрементируем
 * эпоху, чистим все зарегистрированные кэши и уведомляем подписчиков —
 * Preview и Export пересчитывают переносы по реальным метрикам.
 */

import { useSyncExternalStore } from "react"

let epoch = 0
let initialized = false
const listeners = new Set<() => void>()
const cacheClearers = new Set<() => void>()

function bump() {
  epoch += 1
  cacheClearers.forEach((clear) => clear())
  listeners.forEach((l) => l())
}

function ensureSubscribed() {
  if (initialized || typeof document === "undefined" || !document.fonts) return
  initialized = true
  document.fonts.ready.then(bump).catch(() => {})
  document.fonts.addEventListener?.("loadingdone", bump)
}

/** Регистрирует очистку кэша вёрстки при смене эпохи шрифтов. */
export function registerLayoutCacheClearer(fn: () => void): void {
  cacheClearers.add(fn)
  ensureSubscribed()
}

/** Текущая эпоха шрифтов (для использования в ключах кэша). */
export function getFontsEpoch(): number {
  ensureSubscribed()
  return epoch
}

/** React-хук: перерисовывает потребителя при загрузке новых шрифтов. */
export function useFontsEpoch(): number {
  return useSyncExternalStore(
    (cb) => {
      ensureSubscribed()
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => epoch,
    () => 0
  )
}

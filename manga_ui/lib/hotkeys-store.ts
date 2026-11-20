"use client"

// manga_ui/lib/hotkeys-store.ts
/**
 * Синглтон-стор конфигурации горячих клавиш.
 *
 * Раньше каждый экземпляр useHotkeysConfig (десятки на страницу) парсил
 * localStorage и вешал собственные слушатели window/storage. Теперь состояние
 * живёт в модуле, а компоненты подписываются через useSyncExternalStore.
 */

import { useCallback, useSyncExternalStore } from "react"
import {
  type HotkeyConfig,
  type HotkeyActionId,
  DEFAULT_HOTKEYS,
  HOTKEYS_UPDATED_EVENT,
  loadHotkeys,
  saveHotkeys,
} from "@/lib/hotkeys"

let snapshot: HotkeyConfig | null = null
const listeners = new Set<() => void>()

function emit(): void {
  listeners.forEach((listener) => listener())
}

function getSnapshot(): HotkeyConfig {
  if (snapshot === null) snapshot = loadHotkeys()
  return snapshot
}

// Один общий слушатель на весь модуль вместо подписки в каждом компоненте.
let globalListenersAttached = false
function ensureGlobalListeners(): void {
  if (globalListenersAttached || typeof window === "undefined") return
  globalListenersAttached = true
  const syncFromStorage = () => {
    snapshot = loadHotkeys()
    emit()
  }
  window.addEventListener(HOTKEYS_UPDATED_EVENT, syncFromStorage)
  window.addEventListener("storage", syncFromStorage)
}

function subscribe(listener: () => void): () => void {
  ensureGlobalListeners()
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export interface UseHotkeysConfigReturn {
  hotkeys: HotkeyConfig
  updateHotkey: (action: HotkeyActionId, patch: Partial<HotkeyConfig[HotkeyActionId]>) => void
  resetHotkeys: () => void
}

export function useHotkeysConfig(): UseHotkeysConfigReturn {
  const hotkeys = useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_HOTKEYS)

  const updateHotkey = useCallback(
    (action: HotkeyActionId, patch: Partial<HotkeyConfig[HotkeyActionId]>) => {
      const prev = getSnapshot()
      const next: HotkeyConfig = {
        ...prev,
        [action]: { ...prev[action], ...patch },
      }
      snapshot = next
      saveHotkeys(next)
      emit()
    },
    []
  )

  const resetHotkeys = useCallback(() => {
    const next: HotkeyConfig = { ...DEFAULT_HOTKEYS }
    snapshot = next
    saveHotkeys(next)
    emit()
  }, [])

  return { hotkeys, updateHotkey, resetHotkeys }
}

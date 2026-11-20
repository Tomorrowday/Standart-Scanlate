// manga_ui/lib/typeset/page-image-metrics.ts
// Общие метрики (naturalWidth / naturalHeight) текущего скана страницы для синхронной верстки на скане и в карточках

import { useSyncExternalStore } from "react"

export interface PageImageMetrics {
  naturalW: number
  naturalH: number
  /** Реальный отображаемый размер скана — для нормализации JP-плашек. */
  clientW: number
  clientH: number
}

let currentMetrics: PageImageMetrics = {
  naturalW: 1100,
  naturalH: 1600,
  clientW: 1100,
  clientH: 1600,
}

const listeners = new Set<() => void>()

export function setPageImageMetrics(
  naturalW: number,
  naturalH: number,
  clientW?: number,
  clientH?: number
): void {
  const w = naturalW > 0 ? naturalW : 1100
  const h = naturalH > 0 ? naturalH : 1600
  const cw = clientW && clientW > 0 ? clientW : w
  const ch = clientH && clientH > 0 ? clientH : h
  if (
    currentMetrics.naturalW === w &&
    currentMetrics.naturalH === h &&
    currentMetrics.clientW === cw &&
    currentMetrics.clientH === ch
  ) {
    return
  }
  currentMetrics = { naturalW: w, naturalH: h, clientW: cw, clientH: ch }
  listeners.forEach((l) => l())
}

export function getPageImageMetrics(): PageImageMetrics {
  return currentMetrics
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function usePageImageMetrics(): PageImageMetrics {
  return useSyncExternalStore(subscribe, getPageImageMetrics, getPageImageMetrics)
}

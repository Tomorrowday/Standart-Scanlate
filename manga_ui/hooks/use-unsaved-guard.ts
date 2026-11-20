// manga_ui/hooks/use-unsaved-guard.ts
// Защита несохранённых правок при закрытии/скрытии вкладки:
// beforeunload-предупреждение + best-effort keepalive-сохранение.

import { useEffect } from "react"
import type { MutableRefObject } from "react"
import type { PageItem, TextBlock } from "@/lib/types"
import { savePageBlocksKeepalive, toPageBlocksPayload } from "@/lib/api"

export interface UseUnsavedGuardParams {
  isDirtyRef: MutableRefObject<boolean>
  currentPageRef: MutableRefObject<PageItem | null>
  textBlocksRef: MutableRefObject<TextBlock[]>
}

export function useUnsavedGuard({
  isDirtyRef,
  currentPageRef,
  textBlocksRef,
}: UseUnsavedGuardParams): void {
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!isDirtyRef.current) return
      // Браузер покажет собственный диалог подтверждения.
      e.preventDefault()
      e.returnValue = ""
    }

    const flushKeepalive = () => {
      const page = currentPageRef.current
      if (!page || !isDirtyRef.current) return
      savePageBlocksKeepalive(page.id, toPageBlocksPayload(textBlocksRef.current))
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") flushKeepalive()
    }

    window.addEventListener("beforeunload", handleBeforeUnload)
    window.addEventListener("pagehide", flushKeepalive)
    document.addEventListener("visibilitychange", handleVisibilityChange)

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload)
      window.removeEventListener("pagehide", flushKeepalive)
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [isDirtyRef, currentPageRef, textBlocksRef])
}

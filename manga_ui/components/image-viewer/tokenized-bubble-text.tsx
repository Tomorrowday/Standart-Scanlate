// manga_ui/components/image-viewer/tokenized-bubble-text.tsx
// Интерактивный токенизированный японский текст бабла:
// - Слитный рендеринг <span> внутри <div lang="ja"> (100% совместимость с внешними Yomitan / Rikaikun)
// - Изумрудная подсветка терминов Глоссария тайтла, фиолетовая — имён собственных (NER)
// - Всплывающая карточка словаря в FloatingPortal с safePolygon (@floating-ui/react)
// - Добавление/редактирование термина в Глоссарий тайтла в 1 клик и подстановка Speaker

"use client"

import React from "react"
import type { GlossaryHit, TokenSpan } from "@/lib/api/dictionary"
import { InteractiveTokenSpan } from "./tokenized-token-span"

export interface TokenizedBubbleTextProps {
  japText: string
  tokens: TokenSpan[] | null
  titleId?: number | null
  onGlossaryUpdated?: (hit: GlossaryHit) => void
  onSetSpeaker?: (speakerName: string) => void
  onStartEdit?: (e: React.MouseEvent) => void
}

export function TokenizedBubbleText({
  japText,
  tokens,
  titleId,
  onGlossaryUpdated,
  onSetSpeaker,
  onStartEdit,
}: TokenizedBubbleTextProps) {
  // Пока токены загружаются или если они пусты — рендерим плоский текст без скачков верстки
  if (!tokens || tokens.length === 0) {
    return (
      <div
        lang="ja"
        onDoubleClick={onStartEdit}
        className="select-text cursor-text tracking-wide"
      >
        {japText}
      </div>
    )
  }

  // Важно: внутри <div lang="ja"> спаны рендерятся слитно без пробелов,
  // чтобы внешние браузерные расширения Yomitan / Rikaikun читали непрерывный текстовый узел.
  return (
    <div
      lang="ja"
      onDoubleClick={onStartEdit}
      className="select-text tracking-wide"
    >
      {tokens.map((token, idx) => (
        <InteractiveTokenSpan
          key={`${idx}-${token.surface}`}
          token={token}
          titleId={titleId}
          onGlossaryUpdated={onGlossaryUpdated}
          onSetSpeaker={onSetSpeaker}
          onStartEdit={onStartEdit}
        />
      ))}
    </div>
  )
}

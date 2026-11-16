// manga_ui/components/image-viewer/tokenized-token-span.tsx
// Интерактивный спан токена: Floating UI, hover с safePolygon и модульный координатор
// активной карточки словаря (одновременно открыта максимум одна подсказка)

"use client"

import React, { useState, useRef, useEffect } from "react"
import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  useHover,
  useFocus,
  useDismiss,
  useInteractions,
  safePolygon,
  FloatingPortal,
} from "@floating-ui/react"
import type { GlossaryHit, TokenSpan } from "@/lib/api/dictionary"
import { DictionaryPopupCard } from "./dictionary-popup-card"

// Модульный координатор активной карточки словаря:
// одновременно открыта максимум одна подсказка, поэтому при наведении на новое слово
// предыдущая закрывается синхронно, а не висит второй плашкой рядом.
let closeActiveTooltip: (() => void) | null = null

export interface InteractiveTokenSpanProps {
  token: TokenSpan
  titleId?: number | null
  onGlossaryUpdated?: (hit: GlossaryHit) => void
  onSetSpeaker?: (speakerName: string) => void
  onStartEdit?: (e: React.MouseEvent) => void
}

export function InteractiveTokenSpan({
  token,
  titleId,
  onGlossaryUpdated,
  onSetSpeaker,
  onStartEdit,
}: InteractiveTokenSpanProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isFormExpanded, setIsFormExpanded] = useState(false)

  // Собственный «закрыватель» регистрируется в модульном координаторе при открытии.
  const closeSelfRef = useRef<(() => void) | null>(null)
  if (!closeSelfRef.current) {
    closeSelfRef.current = () => setIsOpen(false)
  }

  // Снимаем регистрацию при размонтировании, чтобы не дёргать мёртвый компонент.
  useEffect(() => {
    return () => {
      if (closeActiveTooltip === closeSelfRef.current) {
        closeActiveTooltip = null
      }
    }
  }, [])

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: (open) => {
      const self = closeSelfRef.current
      if (open) {
        // Сначала синхронно гасим чужую открытую карточку — второй словарь не появляется.
        if (closeActiveTooltip && closeActiveTooltip !== self) {
          closeActiveTooltip()
        }
        closeActiveTooltip = self
      } else if (closeActiveTooltip === self) {
        closeActiveTooltip = null
      }

      setIsOpen(open)
      if (!open) {
        setIsFormExpanded(false)
      }
    },
    placement: "top-start",
    whileElementsMounted: autoUpdate,
    middleware: [
      // Подсказка отодвинута от текста, чтобы не перехватывать курсор на следующей строке
      offset(14),
      flip({ fallbackAxisSideDirection: "end", padding: 12 }),
      shift({ padding: 12 }),
    ],
  })

  const hover = useHover(context, {
    // Пока открыта форма добавления в глоссарий, уход курсора не должен
    // закрывать попап и сбрасывать введённый перевод термина.
    enabled: !isFormExpanded,
    move: false,
    // Быстрое закрытие: при переходе на соседнее слово старый тултип успевает уйти
    delay: { open: 70, close: 75 },
    handleClose: safePolygon({ blockPointerEvents: true }),
  })
  const focus = useFocus(context)
  const dismiss = useDismiss(context)

  const { getReferenceProps, getFloatingProps } = useInteractions([hover, focus, dismiss])

  const isGlossary = Boolean(token.glossary_match)
  const isNamedEntity = Boolean(
    !isGlossary &&
      (token.ner_label === "PERSON" ||
        token.ner_label === "LOC" ||
        token.ner_label === "PROPN" ||
        token.pos_ru === "Имя собственное")
  )
  const hasDictEntries = token.dict_entries && token.dict_entries.length > 0

  // Пунктуация и одиночные частицы без статей рендерятся как чистый текстовый спан
  if (token.is_punct_or_particle && !isGlossary && !isNamedEntity && !hasDictEntries) {
    return <span onDoubleClick={onStartEdit}>{token.surface}</span>
  }

  let spanClassName =
    "cursor-pointer border-b border-transparent hover:border-sky-400/80 hover:bg-sky-500/15 transition-colors rounded-[2px]"
  if (isGlossary) {
    spanClassName =
      "cursor-pointer text-emerald-300 font-semibold border-b-2 border-emerald-500/80 hover:bg-emerald-500/20 transition-colors rounded-[2px]"
  } else if (isNamedEntity) {
    spanClassName =
      "cursor-pointer text-purple-200 border-b border-dashed border-purple-400/80 hover:bg-purple-500/20 transition-colors rounded-[2px]"
  }

  return (
    <>
      <span
        ref={refs.setReference}
        {...getReferenceProps({
          onDoubleClick: onStartEdit,
        })}
        className={spanClassName}
      >
        {token.surface}
      </span>

      {isOpen && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            style={floatingStyles}
            {...getFloatingProps({
              onMouseDown: (e) => e.stopPropagation(),
              onClick: (e) => e.stopPropagation(),
            })}
            className="z-[9999] w-80 max-w-sm rounded-xl bg-slate-900/98 border border-slate-700/90 p-3.5 text-slate-100 shadow-2xl backdrop-blur-md text-xs leading-relaxed font-sans select-text"
          >
            <DictionaryPopupCard
              token={token}
              isNamedEntity={isNamedEntity}
              titleId={titleId}
              onGlossaryUpdated={onGlossaryUpdated}
              onSetSpeaker={onSetSpeaker}
              onFormExpandedChange={setIsFormExpanded}
            />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

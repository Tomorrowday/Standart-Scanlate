// manga_ui/components/image-viewer/dictionary-popup-card.tsx
// UI всплывающей карточки словаря: шапка слова, цепочка инфлексий,
// плашка «Из глоссария тайтла» с кнопкой «В Speaker», статьи Warodai/JMdict и форма глоссария

"use client"

import { BookMarked, UserPlus, Sparkles } from "lucide-react"
import type { GlossaryHit, TokenSpan } from "@/lib/api/dictionary"
import { GlossaryQuickForm } from "./glossary-quick-form"

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  warodai: {
    label: "Warodai",
    cls: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  },
  jmdict_ru: {
    label: "JMdict RU",
    cls: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  },
  jmdict_en: {
    label: "JMdict EN",
    cls: "bg-slate-700 text-slate-300 border-slate-600",
  },
  jmnedict: {
    label: "Имена",
    cls: "bg-purple-500/20 text-purple-300 border-purple-500/40",
  },
}

export interface DictionaryPopupCardProps {
  token: TokenSpan
  isNamedEntity: boolean
  titleId?: number | null
  onGlossaryUpdated?: (hit: GlossaryHit) => void
  onSetSpeaker?: (speakerName: string) => void
  onFormExpandedChange?: (expanded: boolean) => void
}

export function DictionaryPopupCard({
  token,
  isNamedEntity,
  titleId,
  onGlossaryUpdated,
  onSetSpeaker,
  onFormExpandedChange,
}: DictionaryPopupCardProps) {
  const hasDictEntries = Boolean(token.dict_entries && token.dict_entries.length > 0)

  return (
    <>
      {/* Шапка карточки: Лемма 【Чтение】, поверхностная форма и цепочка спряжений */}
      <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2">
        <div className="min-w-0">
          <div className="flex items-baseline flex-wrap gap-1.5">
            <span lang="ja" className="text-base font-bold text-white tracking-wide">
              {token.lemma || token.surface}
            </span>
            {token.reading && token.reading !== (token.lemma || token.surface) && (
              <span lang="ja" className="text-xs font-medium text-sky-300">
                【{token.reading}】
              </span>
            )}
          </div>

          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px] text-slate-400">
            {token.surface !== token.lemma && (
              <span>
                в тексте: <span lang="ja" className="text-slate-200 font-medium">{token.surface}</span> •
              </span>
            )}
            <span className="text-indigo-300 font-medium">{token.pos_ru}</span>
            {isNamedEntity && (
              <span className="rounded bg-purple-500/25 border border-purple-500/40 px-1.5 py-0.2 text-[9px] font-semibold text-purple-200">
                {token.ner_label === "PERSON" ? "Имя / Персонаж" : "Имя собств."}
              </span>
            )}
          </div>

          {token.inflection_chain && token.inflection_chain.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {token.inflection_chain.map((reason, rIdx) => (
                <span
                  key={rIdx}
                  className="rounded bg-indigo-500/20 border border-indigo-500/30 px-1.5 py-0.5 text-[10px] font-medium text-indigo-200"
                >
                  {reason}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Приоритетный блок Глоссария тайтла */}
      {token.glossary_match && (
        <div className="mt-2.5 rounded-lg bg-emerald-950/70 border border-emerald-500/40 p-2.5 text-emerald-100">
          <div className="flex items-center justify-between gap-1 text-[10px] uppercase tracking-wider text-emerald-400 font-bold">
            <span className="flex items-center gap-1">
              <BookMarked className="h-3 w-3" />
              Из глоссария тайтла
            </span>
            {onSetSpeaker && (
              <button
                type="button"
                onClick={() => onSetSpeaker(token.glossary_match!.rus_word)}
                className="flex items-center gap-0.5 rounded bg-emerald-800/60 hover:bg-emerald-700 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-100 transition-colors normal-case"
                title="Установить это имя в поле Speaker текущего бабла"
              >
                <UserPlus className="h-2.5 w-2.5" />
                В Speaker
              </button>
            )}
          </div>
          <div className="mt-1 text-sm font-bold text-white">
            {token.glossary_match.rus_word}
          </div>
          {token.glossary_match.context && (
            <div className="mt-0.5 text-[11px] text-emerald-300/90 italic">
              {token.glossary_match.context}
            </div>
          )}
        </div>
      )}

      {/* Список словарных статей (Warodai + JMdict RU/EN) */}
      <div className="mt-2.5 max-h-48 overflow-y-auto space-y-2 pr-1">
        {hasDictEntries ? (
          token.dict_entries.map((entry, idx) => {
            const badge = SOURCE_BADGE[entry.source] || SOURCE_BADGE.jmdict_ru
            return (
              <div key={idx} className="border-l-2 border-slate-700 pl-2">
                <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                  <span className={`rounded border px-1.5 py-0.2 text-[9px] font-semibold ${badge.cls}`}>
                    {badge.label}
                  </span>
                  {entry.kanji !== token.lemma && (
                    <span lang="ja" className="text-[11px] font-semibold text-slate-200">
                      {entry.kanji}
                    </span>
                  )}
                  {entry.reading && (
                    <span lang="ja" className="text-[10px] text-sky-300/90">
                      [{entry.reading}]
                    </span>
                  )}
                  {entry.pos && (
                    <span className="text-[10px] text-slate-400 truncate max-w-[140px]">
                      {entry.pos}
                    </span>
                  )}
                </div>
                <ol className="list-decimal list-inside space-y-0.5 text-slate-200">
                  {entry.meanings.slice(0, 4).map((m, mIdx) => (
                    <li key={mIdx} className="leading-snug break-words">
                      {m}
                    </li>
                  ))}
                </ol>
              </div>
            )
          })
        ) : (
          !token.glossary_match && (
            <div className="text-slate-400 italic py-1 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-slate-500 shrink-0" />
              <span>
                {isNamedEntity
                  ? "Распознано как имя собственное — добавьте в глоссарий тайтла ниже"
                  : "Точное словарное совпадение не найдено"}
              </span>
            </div>
          )
        )}
      </div>

      <GlossaryQuickForm
        token={token}
        titleId={titleId}
        onGlossaryUpdated={onGlossaryUpdated}
        onExpandedChange={onFormExpandedChange}
      />
    </>
  )
}

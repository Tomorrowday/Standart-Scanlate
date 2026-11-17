// manga_ui/components/image-viewer/glossary-quick-form.tsx
// Мини-форма быстрого добавления/редактирования термина в глоссарий тайтла в 1 клик
// (кнопка «В глоссарий», поля jap/rus/context, состояние сохранения)

"use client"

import React, { useRef, useState } from "react"
import { Plus, Check } from "lucide-react"
import type { GlossaryHit, TokenSpan } from "@/lib/api/dictionary"
import { upsertGlossaryFromDictionary } from "@/lib/api/dictionary"

export interface GlossaryQuickFormProps {
  token: TokenSpan
  titleId?: number | null
  onGlossaryUpdated?: (hit: GlossaryHit) => void
  /** Форма раскрыта — родительская карточка не должна закрываться по уходу курсора. */
  onExpandedChange?: (expanded: boolean) => void
}

export function GlossaryQuickForm({
  token,
  titleId,
  onGlossaryUpdated,
  onExpandedChange,
}: GlossaryQuickFormProps) {
  const [isAddingGlossary, setIsAddingGlossary] = useState(false)
  const [japInput, setJapInput] = useState("")
  const [ruInput, setRuInput] = useState("")
  const [contextInput, setContextInput] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const ruInputRef = useRef<HTMLInputElement>(null)

  if (!titleId) return null

  const handleOpenGlossaryForm = (e: React.MouseEvent) => {
    e.stopPropagation()
    setIsAddingGlossary(true)
    onExpandedChange?.(true)
    setJapInput(token.glossary_match?.jap_word || token.lemma || token.surface)
    setRuInput(token.glossary_match?.rus_word || "")
    setContextInput(
      token.glossary_match?.context ||
        (token.ner_label === "PERSON" ? "Персонаж" : token.ner_label === "LOC" ? "Локация" : "")
    )
    setTimeout(() => ruInputRef.current?.focus(), 20)
  }

  const handleCancelGlossaryForm = () => {
    setIsAddingGlossary(false)
    onExpandedChange?.(false)
  }

  const handleSaveGlossary = async (e: React.FormEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!titleId || !japInput.trim() || !ruInput.trim() || isSaving) return

    setIsSaving(true)
    try {
      const saved = await upsertGlossaryFromDictionary({
        title_id: titleId,
        jap_word: japInput.trim(),
        rus_word: ruInput.trim(),
        context: contextInput.trim(),
      })
      onGlossaryUpdated?.(saved)
      setIsAddingGlossary(false)
      onExpandedChange?.(false)
      setJustSaved(true)
      setTimeout(() => setJustSaved(false), 1800)
    } catch (err) {
      alert("Не удалось сохранить в глоссарий: " + String(err))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="mt-3 border-t border-slate-800 pt-2">
      {justSaved ? (
        <div className="flex items-center justify-center gap-1 rounded bg-emerald-950/80 border border-emerald-500/40 py-1 px-2 text-[11px] font-semibold text-emerald-300">
          <Check className="h-3.5 w-3.5" />
          Сохранено в глоссарий тайтла!
        </div>
      ) : !isAddingGlossary ? (
        <button
          type="button"
          onClick={handleOpenGlossaryForm}
          className="flex w-full items-center justify-center gap-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-300 font-medium py-1.5 px-2 text-center transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>
            {token.glossary_match ? "Изменить в глоссарии тайтла" : "В глоссарий тайтла"}
          </span>
        </button>
      ) : (
        <form onSubmit={handleSaveGlossary} className="space-y-1.5">
          <div className="flex gap-1.5">
            <input
              type="text"
              value={japInput}
              onChange={(e) => setJapInput(e.target.value)}
              placeholder="Японский..."
              className="w-2/5 rounded bg-slate-950 border border-slate-700 px-2 py-1 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
            />
            <input
              ref={ruInputRef}
              type="text"
              required
              value={ruInput}
              onChange={(e) => setRuInput(e.target.value)}
              placeholder="Перевод / Имя (Enter)"
              className="w-3/5 rounded bg-slate-950 border border-emerald-600/80 px-2 py-1 text-xs text-white focus:border-emerald-400 focus:outline-none"
            />
          </div>
          <input
            type="text"
            value={contextInput}
            onChange={(e) => setContextInput(e.target.value)}
            placeholder="Контекст / род / кто это (опц.)"
            className="w-full rounded bg-slate-950 border border-slate-800 px-2 py-1 text-[11px] text-slate-300 focus:border-slate-600 focus:outline-none"
          />
          <div className="flex justify-end gap-1.5 pt-0.5">
            <button
              type="button"
              onClick={handleCancelGlossaryForm}
              className="rounded px-2 py-0.5 text-[11px] text-slate-400 hover:text-slate-200"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isSaving || !ruInput.trim()}
              className="rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-2.5 py-0.5 text-[11px] font-semibold text-white transition-colors"
            >
              {isSaving ? "..." : "Сохранить"}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

// manga_ui/components/settings-modal/settings-parameters-tab.tsx
// Вкладка «Параметры и Модели»: модели детектора и клинера, Confidence,
// стандартные шрифты по типам баблов и статус локального сервера Ollama

"use client"

import { Scan, Sparkles, ScanText, Brush } from "lucide-react"
import { MANGA_FONTS } from "@/lib/hotkeys"
import { OllamaStatusCard, type OllamaStatus } from "@/components/settings-modal/ollama-status-card"
import {
  DictionaryStatusCard,
  type DictNlpMode,
} from "@/components/settings-modal/dictionary-status-card"

export interface SettingsParametersTabProps {
  availableDetectors: Record<string, string>
  availableCleaners: Record<string, string>
  detectorModel: string
  onDetectorModelChange: (value: string) => void
  availableOcrModels: Record<string, string>
  ocrModel: string
  onOcrModelChange: (value: string) => void
  cleanModel: string
  onCleanModelChange: (value: string) => void
  availableBrushModels: Record<string, string>
  brushModel: string
  onBrushModelChange: (value: string) => void
  brushThreshold: number
  onBrushThresholdChange: (value: number) => void
  brushExtraDilate: number
  onBrushExtraDilateChange: (value: number) => void
  brushMaxSide: number
  onBrushMaxSideChange: (value: number) => void
  detectConf: number
  onDetectConfChange: (value: number) => void
  fontBubble: string
  onFontBubbleChange: (value: string) => void
  fontThought: string
  onFontThoughtChange: (value: string) => void
  fontSfx: string
  onFontSfxChange: (value: string) => void
  dictNlpMode: DictNlpMode
  onDictNlpModeChange: (value: DictNlpMode) => void
  ollamaStatus: OllamaStatus
  ollamaModels: string[]
  onRefreshOllama: () => void
}

export function SettingsParametersTab({
  availableDetectors,
  availableCleaners,
  detectorModel,
  onDetectorModelChange,
  availableOcrModels,
  ocrModel,
  onOcrModelChange,
  cleanModel,
  onCleanModelChange,
  availableBrushModels,
  brushModel,
  onBrushModelChange,
  brushThreshold,
  onBrushThresholdChange,
  brushExtraDilate,
  onBrushExtraDilateChange,
  brushMaxSide,
  onBrushMaxSideChange,
  detectConf,
  onDetectConfChange,
  fontBubble,
  onFontBubbleChange,
  fontThought,
  onFontThoughtChange,
  fontSfx,
  onFontSfxChange,
  dictNlpMode,
  onDictNlpModeChange,
  ollamaStatus,
  ollamaModels,
  onRefreshOllama,
}: SettingsParametersTabProps) {
  return (
    <div className="space-y-4">

      {/* Модель детектора */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300">
              <Scan className="h-3.5 w-3.5 text-indigo-400" />
              Модель детектора (weights/detect-bubble)
            </label>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Нейросеть YOLO для поиска баблов и текста.
            </p>
          </div>

          <select
            value={detectorModel}
            onChange={(e) => onDetectorModelChange(e.target.value)}
            className="w-56 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-indigo-500"
          >
            {Object.entries(availableDetectors).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Модель OCR */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300">
              <ScanText className="h-3.5 w-3.5 text-sky-400" />
              Модель распознавания OCR (weights/ocr)
            </label>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Нейросеть для чтения текста в баблах (MangaOCR, Hayai Supernova, CPT, PaddleOCR-VL).
            </p>
          </div>

          <select
            value={ocrModel}
            onChange={(e) => onOcrModelChange(e.target.value)}
            className="w-56 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-indigo-500"
          >
            {Object.entries(availableOcrModels).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Модель клина */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300">
              <Sparkles className="h-3.5 w-3.5 text-pink-400" />
              Модель клина (weights/clean-lama)
            </label>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Нейросеть Inpainting для удаления звуков и фона.
            </p>
          </div>

          <select
            value={cleanModel}
            onChange={(e) => onCleanModelChange(e.target.value)}
            className="w-56 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-indigo-500"
          >
            {Object.entries(availableCleaners).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Модель мазка текста (U-Net, weights/brush) */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300">
              <Brush className="h-3.5 w-3.5 text-emerald-400" />
              Модель мазка текста (weights/brush)
            </label>
            <p className="mt-0.5 max-w-md text-[11px] text-slate-500">
              U-Net строит маску для Free-Text (класс 2) и для ручного режима LaMa у любого типа бабла. В Clean Auto баблы речи/мыслей клинятся белым, SFX — эвристикой OpenCV.
            </p>
          </div>

          <select
            value={brushModel}
            onChange={(e) => onBrushModelChange(e.target.value)}
            className="w-56 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-indigo-500"
          >
            {Object.entries(availableBrushModels).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <span className="text-[11px] font-medium text-slate-400">Порог маски</span>
            <p className="text-[10px] text-slate-500">Ниже — чаще срабатывает, выше — консервативнее.</p>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="0.20"
              max="0.80"
              step="0.05"
              value={brushThreshold}
              onChange={(e) => onBrushThresholdChange(parseFloat(e.target.value))}
              className="h-1.5 w-32 cursor-pointer accent-emerald-500"
            />
            <span className="w-12 text-center font-mono text-xs font-bold text-emerald-300 rounded bg-slate-900 px-2 py-1 border border-slate-800">
              {brushThreshold.toFixed(2)}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <span className="text-[11px] font-medium text-slate-400">Расширение маски (px)</span>
            <p className="text-[10px] text-slate-500">0 — как предсказала сеть, минус — эрозия.</p>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="-4"
              max="8"
              step="1"
              value={brushExtraDilate}
              onChange={(e) => onBrushExtraDilateChange(parseInt(e.target.value, 10))}
              className="h-1.5 w-32 cursor-pointer accent-emerald-500"
            />
            <span className="w-12 text-center font-mono text-xs font-bold text-emerald-300 rounded bg-slate-900 px-2 py-1 border border-slate-800">
              {brushExtraDilate > 0 ? `+${brushExtraDilate}` : brushExtraDilate}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <span className="text-[11px] font-medium text-slate-400">Размер входа</span>
            <p className="text-[10px] text-slate-500">Должен совпадать с imgsz обучения модели.</p>
          </div>
          <select
            value={brushMaxSide}
            onChange={(e) => onBrushMaxSideChange(parseInt(e.target.value, 10))}
            className="w-28 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-emerald-500"
          >
            {[512, 640, 768, 896, 1024].map((size) => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Порог детекции (Confidence) */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300">
              Порог срабатывания детектора (Confidence)
            </label>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Регулирует чувствительность к мелким звукам и артефактам.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="range"
              min="0.10"
              max="0.80"
              step="0.05"
              value={detectConf}
              onChange={(e) => onDetectConfChange(parseFloat(e.target.value))}
              className="h-1.5 w-32 cursor-pointer accent-indigo-500"
            />
            <span className="w-12 text-center font-mono text-xs font-bold text-indigo-300 rounded bg-slate-900 px-2 py-1 border border-slate-800">
              {detectConf.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Стандартные шрифты по типам */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-3">
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
          Стандартный шрифт по типу бабла
        </label>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <span className="block text-[11px] font-medium text-emerald-400 mb-1">
              Речь (Тип 0):
            </span>
            <select
              value={fontBubble}
              onChange={(e) => onFontBubbleChange(e.target.value)}
              className="w-full rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500"
            >
              {MANGA_FONTS.map((f) => (
                <option key={f.id} value={f.id}>{f.label}</option>
              ))}
            </select>
          </div>

          <div>
            <span className="block text-[11px] font-medium text-sky-400 mb-1">
              Мысли (Тип 1):
            </span>
            <select
              value={fontThought}
              onChange={(e) => onFontThoughtChange(e.target.value)}
              className="w-full rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500"
            >
              {MANGA_FONTS.map((f) => (
                <option key={f.id} value={f.id}>{f.label}</option>
              ))}
            </select>
          </div>

          <div>
            <span className="block text-[11px] font-medium text-purple-400 mb-1">
              Текст/SFX (Тип 2):
            </span>
            <select
              value={fontSfx}
              onChange={(e) => onFontSfxChange(e.target.value)}
              className="w-full rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500"
            >
              {MANGA_FONTS.map((f) => (
                <option key={f.id} value={f.id}>{f.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Локальный словарь Warodai + JMdict RU и режим NLP */}
      <DictionaryStatusCard
        dictNlpMode={dictNlpMode}
        onDictNlpModeChange={onDictNlpModeChange}
      />

      {/* Статус Ollama */}
      <OllamaStatusCard
        status={ollamaStatus}
        models={ollamaModels}
        onRefresh={onRefreshOllama}
      />

    </div>
  )
}

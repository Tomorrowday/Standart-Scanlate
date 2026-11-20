"use client"

// manga_ui/components/image-viewer.tsx
/**
 * Контракт вьювера страницы манги (разметка баблов, масштабирование, ретушь кистью, режим проверки японского текста).
 */

import type React from "react"
import { useRef, useState, useCallback, useEffect, useMemo } from "react"
import { FolderOpen, Loader2 } from "lucide-react"
import type { TextBlock } from "@/lib/types"
import { setPageImageMetrics, usePageImageMetrics } from "@/lib/typeset"
import { releaseVram, type BrushMaskRect } from "@/lib/api/pages"
import { useHotkeysConfig } from "@/hooks/use-manga-hotkeys"
import { useBoxTransform, type DrawRect } from "@/hooks/use-box-transform"
import { useBrushTool, type BrushMode } from "@/hooks/use-brush-tool"
import { BubbleOverlayItem } from "@/components/image-viewer/bubble-overlay-item"
import { computeJapPlatePlacements } from "@/components/image-viewer/jap-overlay-placement"
import { ViewerHeaderToolbar } from "@/components/image-viewer/viewer-header-toolbar"
import { ViewerFooterHints } from "@/components/image-viewer/viewer-footer-hints"

export interface ImageViewerProps {
  imageSrc: string | null
  textBlocks: TextBlock[]
  selectedId: string | null
  titleId?: number | null
  showTypeset?: boolean
  showJapOverlay: boolean
  pageNumber?: number
  hasCleanScan?: boolean
  viewMode: "original" | "clean"
  defaultFontSize?: number
  /** Автоматически превращать пустой бабл речи в овал после ввода перевода. */
  autoOvalBubble?: boolean
  brushSize: number
  onBrushResize: (delta: number) => void
  activeTool: "box" | "brush"
  onToolChange: (tool: "box" | "brush") => void
  onToggleViewMode: () => void
  onSelect: (id: string | null) => void
  onDrawComplete: (rect: DrawRect, img: HTMLImageElement, existingId?: string, rotation?: number) => void
  onUpdateBlock?: (id: string, patch: Partial<TextBlock>) => void
  onUpdateBlockTransient?: (id: string, patch: Partial<TextBlock>) => void
  getHistoryDepth?: () => number
  onTruncateHistory?: (depth: number) => void
  onBrushClean?: (
    maskBase64: string,
    mode: BrushMode,
    maskRect?: BrushMaskRect
  ) => Promise<void>
}

function normalize(a: number, b: number) {
  return { start: Math.min(a, b), size: Math.abs(a - b) }
}

export function ImageViewer({
  imageSrc,
  textBlocks,
  selectedId,
  titleId,
  showTypeset = false,
  showJapOverlay,
  pageNumber,
  hasCleanScan = false,
  viewMode,
  defaultFontSize = 14,
  autoOvalBubble = true,
  brushSize,
  onBrushResize,
  activeTool,
  onToolChange,
  onToggleViewMode,
  onSelect,
  onDrawComplete,
  onUpdateBlock,
  onUpdateBlockTransient,
  getHistoryDepth,
  onTruncateHistory,
  onBrushClean,
}: ImageViewerProps) {
  const imgRef = useRef<HTMLImageElement | null>(null)
  // DOM-узел картинки как state: на первом рендере ref ещё null, а дочерним
  // компонентам он нужен сразу для расчёта вёрстки.
  const [imgEl, setImgEl] = useState<HTMLImageElement | null>(null)
  const setImgRef = useCallback((el: HTMLImageElement | null) => {
    imgRef.current = el
    setImgEl(el)
  }, [])
  const { hotkeys } = useHotkeysConfig()

  const [brushMode, setBrushMode] = useState<BrushMode>("lama")

  const [origin, setOrigin] = useState<{ x: number; y: number } | null>(null)
  const [draft, setDraft] = useState<DrawRect | null>(null)

  // Единственный ResizeObserver на <img>: публикует natural + отображаемый
  // размер в общий стор, из которого читают все баблы и JP-плашки.
  useEffect(() => {
    const img = imgEl
    if (!img) return

    const publish = () => {
      if (!img.naturalWidth || !img.clientWidth || !img.clientHeight) return
      setPageImageMetrics(
        img.naturalWidth,
        img.naturalHeight,
        img.clientWidth,
        img.clientHeight
      )
    }

    publish()
    const observer = new ResizeObserver(publish)
    observer.observe(img)
    window.addEventListener("resize", publish)
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", publish)
    }
  }, [imgEl, imageSrc])

  const pageMetrics = usePageImageMetrics()

  const prevToolRef = useRef(activeTool)
  useEffect(() => {
    if (prevToolRef.current === "brush" && activeTool !== "brush") {
      releaseVram()
    }
    prevToolRef.current = activeTool
  }, [activeTool])

  // Один unmount-cleanup: при смене инструмента VRAM освобождает эффект выше,
  // иначе releaseVram() вызывался дважды (на смене и в cleanup).
  const activeToolRef = useRef(activeTool)
  activeToolRef.current = activeTool
  useEffect(() => {
    return () => {
      if (activeToolRef.current === "brush") {
        releaseVram()
      }
    }
  }, [])

  const pointFromEvent = useCallback((e: React.MouseEvent | MouseEvent) => {
    const img = imgRef.current
    if (!img) return null
    const rect = img.getBoundingClientRect()
    const x = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1)
    const y = Math.min(Math.max((e.clientY - rect.top) / rect.height, 0), 1)
    return { x, y }
  }, [])

  const handleTransformComplete = useCallback(
    (rect: DrawRect, img: HTMLImageElement, id: string, rot: number) => {
      onDrawComplete(rect, img, id, rot)
    },
    [onDrawComplete]
  )

  const { isEditing, editId, editType, activeBox, activeRotation, startTransform } = useBoxTransform(
    imgRef,
    pointFromEvent,
    handleTransformComplete
  )

  const {
    brushCanvasRef,
    cursorRef,
    isBrushProcessing,
    handleBrushMouseDown,
    handleBrushMouseMove,
    handleBrushMouseUp,
    handleBrushMouseLeave,
  } = useBrushTool({
    imgRef,
    brushSize,
    brushMode,
    imageSrc,
    onBrushClean,
    onBrushResize,
  })

  const handleToolChange = (tool: "box" | "brush") => {
    onToolChange(tool)
    if (tool === "box" && cursorRef.current) cursorRef.current.style.display = "none"
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    if (activeTool === "brush") return
    // Правый/средний клик не должен начинать рисовать рамку.
    if (e.button !== 0) return
    if (!imageSrc || isEditing) return
    const p = pointFromEvent(e)
    if (!p) return
    onSelect(null)
    setOrigin(p)
    setDraft({ x: p.x, y: p.y, width: 0, height: 0, rotation: 0 })
  }

  // Свежий черновик для обработчиков window: не пересоздаём подписки на каждый mousemove.
  const draftRef = useRef<DrawRect | null>(null)
  draftRef.current = draft

  const finishDraw = useCallback(() => {
    if (activeTool === "brush") return
    const currentDraft = draftRef.current
    // Гасим черновик сразу: mouseup приходит и в React-обработчик, и в window —
    // повторный вызов не должен создать второй бабл.
    draftRef.current = null
    if (currentDraft && imgRef.current && currentDraft.width > 0.01 && currentDraft.height > 0.01) {
      onDrawComplete(currentDraft, imgRef.current, undefined, 0)
    }
    setOrigin(null)
    setDraft(null)
  }, [activeTool, onDrawComplete])

  // Рисование рамки продолжается, даже если курсор вышел за пределы картинки:
  // завершаем только по mouseup в любом месте окна.
  useEffect(() => {
    if (!origin || activeTool === "brush") return

    const handleWindowMove = (e: MouseEvent) => {
      const p = pointFromEvent(e)
      if (!p) return
      const hx = normalize(origin.x, p.x)
      const hy = normalize(origin.y, p.y)
      setDraft({ x: hx.start, y: hy.start, width: hx.size, height: hy.size, rotation: 0 })
    }

    window.addEventListener("mousemove", handleWindowMove)
    window.addEventListener("mouseup", finishDraw)
    return () => {
      window.removeEventListener("mousemove", handleWindowMove)
      window.removeEventListener("mouseup", finishDraw)
    }
  }, [origin, activeTool, pointFromEvent, finishDraw])

  const visibleBoxes = useMemo(() => {
    return draft ? [...textBlocks, { id: "__draft__", ...draft } as TextBlock] : textBlocks
  }, [textBlocks, draft])

  // Стабильный ключ только от геометрии и japText: правка перевода/стиля не
  // должна пересчитывать тысячи пересечений плашек.
  const japPlacementKey = useMemo(
    () =>
      textBlocks
        .map((b) => `${b.id}|${b.x}|${b.y}|${b.width}|${b.height}|${b.japText ?? ""}`)
        .join("\n"),
    [textBlocks]
  )

  // Централизованный расчёт свободных позиций всех JP-плашек страницы:
  // без перекрытий с баблами и между самими плашками.
  const japPlatePlacements = useMemo(() => {
    if (!showJapOverlay) return {}
    return computeJapPlatePlacements(textBlocks, {
      width: pageMetrics.clientW,
      height: pageMetrics.clientH,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [japPlacementKey, showJapOverlay, pageMetrics.clientW, pageMetrics.clientH])

  return (
    <section className="flex min-h-0 flex-1 min-w-0 flex-col overflow-hidden">
      <ViewerHeaderToolbar
        pageNumber={pageNumber}
        imageSrc={imageSrc}
        activeTool={activeTool}
        brushMode={brushMode}
        brushSize={brushSize}
        viewMode={viewMode}
        hasCleanScan={hasCleanScan}
        hotkeys={hotkeys}
        onToolChange={handleToolChange}
        onBrushModeChange={setBrushMode}
        onBrushResize={onBrushResize}
        onToggleViewMode={onToggleViewMode}
      />

      <div className="min-h-0 flex-1 overflow-auto p-5">
        {!imageSrc ? (
          <div className="flex h-full min-h-[420px] w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-800 bg-slate-900/30 text-slate-500">
            <div className="rounded-full bg-slate-800 p-4 text-indigo-400">
              <FolderOpen className="h-7 w-7" />
            </div>
            <p className="text-sm font-medium text-slate-300">No page selected</p>
            <p className="text-xs text-slate-500">Select a chapter page in the Project Explorer to begin</p>
          </div>
        ) : (
          <div
            className="relative inline-block w-full select-none"
            onMouseDown={handleMouseDown}
            onMouseUp={finishDraw}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              ref={setImgRef}
              crossOrigin="anonymous"
              src={imageSrc}
              alt="Manga page"
              draggable={false}
              onLoad={(e) => {
                const el = e.currentTarget
                setPageImageMetrics(
                  el.naturalWidth,
                  el.naturalHeight,
                  el.clientWidth,
                  el.clientHeight
                )
              }}
              className="block w-full rounded-lg border border-slate-800"
            />

            <canvas
              ref={brushCanvasRef}
              onMouseDown={handleBrushMouseDown}
              onMouseMove={handleBrushMouseMove}
              onMouseUp={handleBrushMouseUp}
              onMouseLeave={handleBrushMouseLeave}
              className={[
                "absolute inset-0 z-30 touch-none",
                activeTool === "brush" ? "pointer-events-auto cursor-none" : "pointer-events-none hidden",
              ].join(" ")}
            />

            {activeTool === "brush" && (
              <div
                ref={cursorRef}
                className="pointer-events-none absolute left-0 top-0 z-50 rounded-full border border-white shadow-[0_0_0_1.5px_rgba(0,0,0,0.85)] will-change-transform"
                style={{
                  width: brushSize,
                  height: brushSize,
                  display: "none",
                }}
              >
                <div className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.9)]" />
              </div>
            )}

            {isBrushProcessing && (
              <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-[1px] rounded-lg">
                <div className="flex items-center gap-2 rounded-lg border border-pink-500/50 bg-slate-950/90 px-3 py-2 text-xs font-medium text-pink-300 shadow-2xl">
                  <Loader2 className="h-4 w-4 animate-spin text-pink-400" />
                  {brushMode === "lama" ? "LaMa Inpainting..." : "Applying fill..."}
                </div>
              </div>
            )}

            {activeTool === "box" &&
              visibleBoxes.map((box, index) => {
                // Транзиентные drag/rotate-данные передаём только текущему баблу:
                // иначе перетаскивание одного ререндерит остальные 25 на 60 fps.
                const isCurrentEdit = isEditing && editId === box.id
                return (
                <BubbleOverlayItem
                  key={box.id}
                  box={box}
                  index={index}
                  titleId={titleId}
                  isSelected={box.id === selectedId}
                  showTypeset={showTypeset}
                  showJapOverlay={showJapOverlay}
                  autoJapPlacement={japPlatePlacements[box.id] ?? null}
                  imgElement={imgEl}
                  isEditingCurrent={isCurrentEdit}
                  editType={isCurrentEdit ? editType : null}
                  activeBox={isCurrentEdit ? activeBox : null}
                  activeRotation={isCurrentEdit ? activeRotation : 0}
                  defaultFontSize={defaultFontSize}
                  autoOvalBubble={autoOvalBubble}
                  onStartTransform={startTransform}
                  onSelect={onSelect}
                  onUpdate={onUpdateBlock}
                  onUpdateTransient={onUpdateBlockTransient}
                  getHistoryDepth={getHistoryDepth}
                  onTruncateHistory={onTruncateHistory}
                />
                )
              })}
          </div>
        )}
      </div>

      {imageSrc && <ViewerFooterHints activeTool={activeTool} brushMode={brushMode} hotkeys={hotkeys} />}
    </section>
  )
}

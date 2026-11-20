// manga_ui/hooks/use-brush-tool.ts
/**
 * Хук кисти ретуши и очистки (холст, мазки, экспорт маски).
 */

import { useRef, useState, useCallback, useEffect } from "react"
import type { BrushMaskRect } from "@/lib/api/pages"

export type BrushMode = "lama" | "white" | "black"

export type BrushWheelModifier = "shift" | "ctrl" | "alt"

/**
 * Модификатор, который нужно зажать вместе с колесом мыши, чтобы изменить
 * размер кисти. Поменяйте значение на "ctrl" или "alt" — обработчик ниже
 * подхватит изменение автоматически.
 */
export const BRUSH_WHEEL_MODIFIER: BrushWheelModifier = "shift"

/** Человекочитаемая подпись модификатора для подсказок в UI. */
export function brushWheelModifierLabel(modifier: BrushWheelModifier): string {
  if (modifier === "ctrl") return "Ctrl"
  if (modifier === "alt") return "Alt"
  return "Shift"
}

export const BRUSH_WHEEL_MODIFIER_LABEL = brushWheelModifierLabel(BRUSH_WHEEL_MODIFIER)

/** Шаг изменения размера кисти за один «щелчок» колеса, px. */
const BRUSH_WHEEL_STEP = 4

function isBrushWheelModifierPressed(e: WheelEvent, modifier: BrushWheelModifier): boolean {
  if (modifier === "ctrl") return e.ctrlKey || e.metaKey
  if (modifier === "alt") return e.altKey
  return e.shiftKey
}

export interface UseBrushToolProps {
  imgRef: React.RefObject<HTMLImageElement | null>
  brushSize: number
  brushMode: BrushMode
  imageSrc: string | null
  onBrushClean?: (maskBase64: string, mode: BrushMode, maskRect?: BrushMaskRect) => Promise<void>
  /** Изменение размера кисти (вызывается колесом мыши с зажатым модификатором). */
  onBrushResize?: (delta: number) => void
}

export interface UseBrushToolReturn {
  brushCanvasRef: React.RefObject<HTMLCanvasElement | null>
  cursorRef: React.RefObject<HTMLDivElement | null>
  isBrushProcessing: boolean
  handleBrushMouseDown: (e: React.MouseEvent<HTMLCanvasElement>) => void
  handleBrushMouseMove: (e: React.MouseEvent<HTMLCanvasElement>) => void
  handleBrushMouseUp: () => Promise<void>
  handleBrushMouseLeave: () => void
}

export function useBrushTool({
  imgRef,
  brushSize,
  brushMode,
  imageSrc,
  onBrushClean,
  onBrushResize,
}: UseBrushToolProps): UseBrushToolReturn {
  const brushCanvasRef = useRef<HTMLCanvasElement>(null)
  const cursorRef = useRef<HTMLDivElement>(null)

  const [isBrushPainting, setIsBrushPainting] = useState<boolean>(false)
  const [isBrushProcessing, setIsBrushProcessing] = useState<boolean>(false)

  // Пока идёт мазок, ResizeObserver/resize не должны перезаписывать размер
  // холста: это мгновенно стирает рисуемый мазок.
  const isBrushPaintingRef = useRef(false)

  // Bounding box текущего мазка в координатах экранного канваса.
  // Позволяет отправлять на бэкенд только кроп маски, а не полноразмерный PNG.
  const strokeBoundsRef = useRef<{
    minX: number
    minY: number
    maxX: number
    maxY: number
  } | null>(null)

  const extendStrokeBounds = useCallback(
    (x: number, y: number) => {
      const r = brushSize / 2 + 2
      const b = strokeBoundsRef.current
      if (!b) {
        strokeBoundsRef.current = { minX: x - r, minY: y - r, maxX: x + r, maxY: y + r }
        return
      }
      b.minX = Math.min(b.minX, x - r)
      b.minY = Math.min(b.minY, y - r)
      b.maxX = Math.max(b.maxX, x + r)
      b.maxY = Math.max(b.maxY, y + r)
    },
    [brushSize]
  )

  const syncBrushCanvasSize = useCallback(() => {
    const canvas = brushCanvasRef.current
    const img = imgRef.current
    if (!canvas || !img) return
    if (isBrushPaintingRef.current) return
    if (img.clientWidth > 0 && img.clientHeight > 0) {
      if (canvas.width !== img.clientWidth || canvas.height !== img.clientHeight) {
        canvas.width = img.clientWidth
        canvas.height = img.clientHeight
      }
    }
  }, [imgRef])

  useEffect(() => {
    syncBrushCanvasSize()
    const img = imgRef.current
    let observer: ResizeObserver | null = null

    if (img && typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => {
        syncBrushCanvasSize()
      })
      observer.observe(img)
    }

    window.addEventListener("resize", syncBrushCanvasSize)
    return () => {
      if (observer) observer.disconnect()
      window.removeEventListener("resize", syncBrushCanvasSize)
    }
  }, [syncBrushCanvasSize, imageSrc, imgRef])

  // Колесо мыши с зажатым модификатором меняет размер кисти. Слушатель нативный:
  // React-обёртка onWheel пассивная и не может отменить прокрутку/зум страницы.
  // Канвас существует только в режиме кисти, поэтому в Box колесо не вмешивается.
  useEffect(() => {
    const canvas = brushCanvasRef.current
    if (!canvas || !onBrushResize) return

    const handleWheel = (e: WheelEvent) => {
      if (!isBrushWheelModifierPressed(e, BRUSH_WHEEL_MODIFIER) || e.deltaY === 0) return
      e.preventDefault()
      onBrushResize(e.deltaY < 0 ? BRUSH_WHEEL_STEP : -BRUSH_WHEEL_STEP)
    }

    canvas.addEventListener("wheel", handleWheel, { passive: false })
    return () => canvas.removeEventListener("wheel", handleWheel)
  }, [onBrushResize, imageSrc])

  const getBrushStrokeStyle = useCallback(() => {
    if (brushMode === "white") return "rgba(255, 255, 255, 0.95)"
    if (brushMode === "black") return "rgba(0, 0, 0, 0.95)"
    return "rgba(236, 72, 153, 0.65)"
  }, [brushMode])

  const getCanvasCoords = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = brushCanvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    }
  }, [])

  const handleBrushMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      // Рисуем кистью только левой кнопкой.
      if (e.button !== 0) return
      if (isBrushProcessing || !onBrushClean) return
      syncBrushCanvasSize()
      const canvas = brushCanvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext("2d")
      if (!ctx) return

      isBrushPaintingRef.current = true
      setIsBrushPainting(true)
      const { x, y } = getCanvasCoords(e)
      strokeBoundsRef.current = null
      extendStrokeBounds(x, y)

      if (cursorRef.current) {
        cursorRef.current.style.display = "block"
        cursorRef.current.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`
      }

      const color = getBrushStrokeStyle()
      ctx.strokeStyle = color
      ctx.fillStyle = color
      ctx.lineWidth = brushSize
      ctx.lineCap = "round"
      ctx.lineJoin = "round"

      ctx.beginPath()
      ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2)
      ctx.fill()

      ctx.beginPath()
      ctx.moveTo(x, y)
    },
    [isBrushProcessing, onBrushClean, syncBrushCanvasSize, getCanvasCoords, getBrushStrokeStyle, brushSize, extendStrokeBounds]
  )

  const handleBrushMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const { x, y } = getCanvasCoords(e)

      if (cursorRef.current) {
        cursorRef.current.style.display = "block"
        cursorRef.current.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`
      }

      if (isBrushPainting) {
        const canvas = brushCanvasRef.current
        if (!canvas) return
        const ctx = canvas.getContext("2d")
        if (!ctx) return

        ctx.lineTo(x, y)
        ctx.stroke()
        extendStrokeBounds(x, y)
      }
    },
    [getCanvasCoords, isBrushPainting, extendStrokeBounds]
  )

  const handleBrushMouseUp = useCallback(async () => {
    if (!isBrushPainting) return
    setIsBrushPainting(false)

    const screenCanvas = brushCanvasRef.current
    const img = imgRef.current
    if (!screenCanvas || !img || !onBrushClean) {
      isBrushPaintingRef.current = false
      return
    }

    // Клик кистью до фактической загрузки картинки/канваса не должен давать Infinity.
    if (
      screenCanvas.width <= 0 ||
      screenCanvas.height <= 0 ||
      img.naturalWidth <= 0 ||
      img.naturalHeight <= 0
    ) {
      console.warn("Кисть: канвас или изображение ещё не готовы")
      isBrushPaintingRef.current = false
      return
    }

    setIsBrushProcessing(true)

    try {
      const scaleX = img.naturalWidth / screenCanvas.width
      const scaleY = img.naturalHeight / screenCanvas.height
      if (!Number.isFinite(scaleX) || !Number.isFinite(scaleY)) {
        console.warn("Кисть: некорректный масштаб канваса", { scaleX, scaleY })
        setIsBrushProcessing(false)
        return
      }

      // Отправляем только кроп маски по bbox мазка (обычно ~200×200 вместо
      // полноразмерного 4K PNG): меньше трафика, CPU и времени отклика.
      const bounds = strokeBoundsRef.current
      strokeBoundsRef.current = null
      const pad = 2
      const cropX = Math.max(0, Math.floor((bounds?.minX ?? 0) - pad))
      const cropY = Math.max(0, Math.floor((bounds?.minY ?? 0) - pad))
      const cropRight = Math.min(screenCanvas.width, Math.ceil((bounds?.maxX ?? screenCanvas.width) + pad))
      const cropBottom = Math.min(screenCanvas.height, Math.ceil((bounds?.maxY ?? screenCanvas.height) + pad))
      const cropW = Math.max(1, cropRight - cropX)
      const cropH = Math.max(1, cropBottom - cropY)

      const natX = Math.max(0, Math.min(img.naturalWidth - 1, Math.floor(cropX * scaleX)))
      const natY = Math.max(0, Math.min(img.naturalHeight - 1, Math.floor(cropY * scaleY)))
      const natW = Math.max(1, Math.min(img.naturalWidth - natX, Math.ceil(cropW * scaleX)))
      const natH = Math.max(1, Math.min(img.naturalHeight - natY, Math.ceil(cropH * scaleY)))

      const offscreen = document.createElement("canvas")
      offscreen.width = natW
      offscreen.height = natH
      const oCtx = offscreen.getContext("2d")

      if (oCtx) {
        oCtx.clearRect(0, 0, natW, natH)
        oCtx.drawImage(screenCanvas, cropX, cropY, cropW, cropH, 0, 0, natW, natH)

        const imgData = oCtx.getImageData(0, 0, natW, natH)
        const d = imgData.data

        for (let i = 0; i < d.length; i += 4) {
          if (d[i + 3] > 15) {
            d[i] = 255
            d[i + 1] = 255
            d[i + 2] = 255
            d[i + 3] = 255
          } else {
            d[i] = 0
            d[i + 1] = 0
            d[i + 2] = 0
            d[i + 3] = 255
          }
        }
        oCtx.putImageData(imgData, 0, 0)

        const maskBase64 = offscreen.toDataURL("image/png")
        const sCtx = screenCanvas.getContext("2d")
        sCtx?.clearRect(0, 0, screenCanvas.width, screenCanvas.height)

        await onBrushClean(maskBase64, brushMode, {
          x: natX,
          y: natY,
          width: natW,
          height: natH,
        })
      }
    } catch (err) {
      console.error("Ошибка применения кисти:", err)
    } finally {
      isBrushPaintingRef.current = false
      setIsBrushProcessing(false)
    }
  }, [isBrushPainting, imgRef, onBrushClean, brushMode])

  const handleBrushMouseLeave = useCallback(() => {
    if (cursorRef.current) {
      cursorRef.current.style.display = "none"
    }
    if (isBrushPainting) {
      handleBrushMouseUp()
    }
  }, [isBrushPainting, handleBrushMouseUp])

  return {
    brushCanvasRef,
    cursorRef,
    isBrushProcessing,
    handleBrushMouseDown,
    handleBrushMouseMove,
    handleBrushMouseUp,
    handleBrushMouseLeave,
  }
}

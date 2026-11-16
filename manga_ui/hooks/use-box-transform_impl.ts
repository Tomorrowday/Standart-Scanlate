// manga_ui/hooks/use-box-transform_impl.ts
// Логика перетаскивания, 8-точечного масштабирования и вращения баблов

import { useState, useEffect, useCallback, useRef } from "react"
import type { TextBlock } from "@/lib/types"
import type { DrawRect, EditAction, UseBoxTransformReturn } from "./use-box-transform"

const MIN_BLOCK_SIZE = 0.008

interface TransformSession {
  startPoint: { x: number; y: number }
  originalBox: DrawRect
  editType: EditAction
  editId: string
  currentRotation: number
}

export function useBoxTransform(
  imgRef: React.RefObject<HTMLImageElement | null>,
  pointFromEvent: (e: React.MouseEvent | MouseEvent) => { x: number; y: number } | null,
  onTransformComplete: (rect: DrawRect, img: HTMLImageElement, id: string, rotation: number) => void
): UseBoxTransformReturn {
  const [isEditing, setIsEditing] = useState(false)
  const [editType, setEditType] = useState<EditAction | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [activeBox, setActiveBox] = useState<DrawRect | null>(null)
  const [activeRotation, setActiveRotation] = useState<number>(0)

  // Рефы для стабильных ссылок без разрыва и переподписки слушателей
  const sessionRef = useRef<TransformSession | null>(null)
  const pointFromEventRef = useRef(pointFromEvent)
  pointFromEventRef.current = pointFromEvent
  const onTransformCompleteRef = useRef(onTransformComplete)
  onTransformCompleteRef.current = onTransformComplete

  const computeUpdatedRect = useCallback((orig: DrawRect, action: EditAction, dx: number, dy: number): DrawRect => {
    const updated = { ...orig }
    const currentRot = orig.rotation || 0

    if (action === "move") {
      updated.x = Math.max(0, Math.min(1 - orig.width, orig.x + dx))
      updated.y = Math.max(0, Math.min(1 - orig.height, orig.y + dy))
      return updated
    }

    let localDx = dx
    let localDy = dy

    if (Math.abs(currentRot) >= 0.5) {
      // Нормализованные доли искажают оси при повороте, если изображение не
      // квадратное: переводим сдвиг в пиксели, поворачиваем и возвращаем обратно.
      const img = imgRef.current
      if (img) {
        const rect = img.getBoundingClientRect()
        if (rect.width > 0 && rect.height > 0) {
          const pxDx = dx * rect.width
          const pxDy = dy * rect.height
          const rad = (-currentRot * Math.PI) / 180
          const rotPxX = pxDx * Math.cos(rad) - pxDy * Math.sin(rad)
          const rotPxY = pxDx * Math.sin(rad) + pxDy * Math.cos(rad)
          localDx = rotPxX / rect.width
          localDy = rotPxY / rect.height
        }
      }
    }

    if (action === "e" || action === "ne" || action === "se") {
      updated.width = Math.max(MIN_BLOCK_SIZE, Math.min(1 - orig.x, orig.width + localDx))
    } else if (action === "w" || action === "nw" || action === "sw") {
      const rightEdge = orig.x + orig.width
      const targetX = Math.max(0, Math.min(rightEdge - MIN_BLOCK_SIZE, orig.x + localDx))
      updated.x = targetX
      updated.width = rightEdge - targetX
    }

    if (action === "s" || action === "se" || action === "sw") {
      updated.height = Math.max(MIN_BLOCK_SIZE, Math.min(1 - orig.y, orig.height + localDy))
    } else if (action === "n" || action === "ne" || action === "nw") {
      const bottomEdge = orig.y + orig.height
      const targetY = Math.max(0, Math.min(bottomEdge - MIN_BLOCK_SIZE, orig.y + localDy))
      updated.y = targetY
      updated.height = bottomEdge - targetY
    }

    return updated
  }, [imgRef])

  const startTransform = useCallback(
    (e: React.MouseEvent, box: TextBlock, action: EditAction) => {
      const p = pointFromEventRef.current(e)
      if (!p) return

      const initialRect: DrawRect = {
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        rotation: box.rotation || 0,
      }

      sessionRef.current = {
        startPoint: p,
        originalBox: initialRect,
        editType: action,
        editId: box.id,
        currentRotation: box.rotation || 0,
      }

      setIsEditing(true)
      setEditType(action)
      setEditId(box.id)
      setActiveBox(initialRect)
      setActiveRotation(box.rotation || 0)
    },
    []
  )

  useEffect(() => {
    if (!isEditing) return

    // Угол считаем по «сырым» координатам курсора без клампинга в [0, 1]:
    // при вращении у края страницы курсор выходит за изображение, и клампинг
    // приводил бы к резким скачкам угла.
    const getRotationDeg = (e: MouseEvent, session: TransformSession) => {
      const img = imgRef.current
      if (!img) return session.currentRotation
      const imgRect = img.getBoundingClientRect()
      const cx = session.originalBox.x + session.originalBox.width / 2
      const cy = session.originalBox.y + session.originalBox.height / 2
      const px = e.clientX - imgRect.left - cx * imgRect.width
      const py = e.clientY - imgRect.top - cy * imgRect.height

      let deg = (Math.atan2(py, px) * 180) / Math.PI + 90
      deg = ((deg + 180) % 360) - 180

      if (Math.abs(deg) < 2.0) deg = 0
      return deg
    }

    const handleGlobalMouseMove = (e: MouseEvent) => {
      const session = sessionRef.current
      if (!session || !imgRef.current) return

      if (session.editType === "rotate") {
        const deg = getRotationDeg(e, session)
        session.currentRotation = deg
        setActiveRotation(deg)
        return
      }

      const p = pointFromEventRef.current(e)
      if (!p) return

      const dx = p.x - session.startPoint.x
      const dy = p.y - session.startPoint.y
      const updated = computeUpdatedRect(session.originalBox, session.editType, dx, dy)
      setActiveBox(updated)
    }

    const handleGlobalMouseUp = (e: MouseEvent) => {
      const session = sessionRef.current
      if (!session || !imgRef.current) return

      if (session.editType === "rotate") {
        const finalRot = Math.round(getRotationDeg(e, session) * 10) / 10
        const origRot = session.originalBox.rotation || 0
        // Клик без реального вращения не должен создавать пустой шаг Undo.
        if (Math.abs(finalRot - origRot) > 0.05) {
          onTransformCompleteRef.current(session.originalBox, imgRef.current, session.editId, finalRot)
        }
      } else {
        const p = pointFromEventRef.current(e)
        if (p) {
          const dx = p.x - session.startPoint.x
          const dy = p.y - session.startPoint.y
          const finalRect = computeUpdatedRect(session.originalBox, session.editType, dx, dy)
          const orig = session.originalBox
          const changed =
            Math.abs(finalRect.x - orig.x) > 1e-4 ||
            Math.abs(finalRect.y - orig.y) > 1e-4 ||
            Math.abs(finalRect.width - orig.width) > 1e-4 ||
            Math.abs(finalRect.height - orig.height) > 1e-4
          // Простой клик/двойной клик по баблу без сдвига не должен
          // записывать холостой снапшот в историю Undo.
          if (changed) {
            onTransformCompleteRef.current(finalRect, imgRef.current, session.editId, orig.rotation || 0)
          }
        }
      }

      sessionRef.current = null
      setIsEditing(false)
      setEditType(null)
      setEditId(null)
      setActiveBox(null)
    }

    window.addEventListener("mousemove", handleGlobalMouseMove)
    window.addEventListener("mouseup", handleGlobalMouseUp)
    return () => {
      window.removeEventListener("mousemove", handleGlobalMouseMove)
      window.removeEventListener("mouseup", handleGlobalMouseUp)
    }
  }, [isEditing, imgRef, computeUpdatedRect])

  return {
    isEditing,
    editId,
    editType,
    activeBox,
    activeRotation,
    startTransform,
  }
}
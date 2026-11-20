// manga_ui/hooks/pipelines/clean-pipeline.ts
// Очистка страницы (клин) и откат клина к исходному скану

import { revertCleanPage, runCleanPage } from "@/lib/api"
import type { PageStatus } from "@/lib/types"
import type { PagePipelineContext } from "./types"

export async function executeCleanPage(
  ctx: PagePipelineContext,
  mode: "auto" | "lama" | "white" = "auto"
): Promise<void> {
  const {
    textBlocks,
    saveBlocks,
    setViewMode,
    onPageStatusUpdate,
    setIsCleaning,
    recordCleanAction,
    discardLastSnapshot,
  } = ctx
  const currentPage = ctx.currentPage
  if (!currentPage) return
  if (textBlocks.length === 0) {
    alert("Сначала добавьте или найдите баблы для очистки.")
    return
  }

  // Фиксируем страницу до await: пользователь мог переключиться, пока идёт клин.
  const targetPageId = currentPage.id
  const { isCurrentPage } = ctx

  setIsCleaning(true)
  try {
    await saveBlocks(true)
    // Бэкенд делает бэкап скана (одна ступень) — добавляем шаг в Undo-стек,
    // чтобы Ctrl+Z откатил и файл клина, а не только разметку.
    recordCleanAction()
    const res = await runCleanPage(targetPageId, mode)
    if (res.success) {
      if (isCurrentPage(targetPageId)) setViewMode("clean")
      onPageStatusUpdate(targetPageId, (res.page_status as PageStatus) || "cleaned", res.clean_path)
    } else {
      if (isCurrentPage(targetPageId)) discardLastSnapshot()
      alert("Ошибка клина: " + res.error)
    }
  } catch (e) {
    if (isCurrentPage(targetPageId)) discardLastSnapshot()
    console.error(e)
    alert("Не удалось очистить страницу")
  } finally {
    setIsCleaning(false)
  }
}

export async function executeRevertClean(ctx: PagePipelineContext): Promise<void> {
  const {
    setCurrentPage,
    setViewMode,
    onPageStatusUpdate,
    setIsRevertingClean,
    isCurrentPage,
  } = ctx
  const currentPage = ctx.currentPage
  if (!currentPage || !currentPage.clean_path) return
  if (!confirm("Откатить клин этой страницы и вернуться к исходному скану?")) return

  const targetPageId = currentPage.id

  setIsRevertingClean(true)
  try {
    const res = await revertCleanPage(targetPageId)
    if (res.success) {
      // Не стираем clean_path у другой страницы, если пользователь переключился.
      setCurrentPage((prev) =>
        prev && prev.id === targetPageId ? { ...prev, clean_path: undefined, status: res.page_status } : prev
      )
      if (isCurrentPage(targetPageId)) setViewMode("original")
      onPageStatusUpdate(targetPageId, res.page_status, "")
    } else {
      alert("Ошибка отката клина: " + (res.error || res.detail))
    }
  } catch (e) {
    alert("Ошибка при откате клина: " + String(e))
  } finally {
    setIsRevertingClean(false)
  }
}

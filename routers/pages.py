# routers/pages.py
"""
Роутер страниц манги (детекция, OCR, клин, откат шага клина, баблы, запекание, отдача сканов).
Зависимости: database, schemas, services.cleaner, services.page_service, cv2, numpy
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import Response

from schemas import SavePageBlocksRequest, SpotCleanRequest
from schemas.blocks import BrushCleanRequest
from routers import pages_handlers as _h

router = APIRouter(prefix="/api/pages", tags=["Pages"])


@router.post("/release-vram")
def release_vram_endpoint():
    """Принудительная очистка кэша видеопамяти."""
    return _h.release_vram_endpoint()


@router.get("/{page_id}")
def get_page_details(page_id: int):
    """Информация о странице и путях к оригинальному и заклиненному сканам."""
    return _h.get_page_details(page_id)


@router.get("/{page_id}/speakers")
def get_page_speakers(page_id: int):
    """Список спикеров тайтла и текущей главы для подсказок."""
    return _h.get_page_speakers(page_id)


@router.get("/{page_id}/image")
def get_page_image(page_id: int) -> Response:
    """Отдача оригинального файла страницы манги."""
    return _h.get_page_image(page_id)


@router.get("/{page_id}/clean-image")
def get_page_clean_image(page_id: int) -> Response:
    """Отдача заклиненного скана страницы (или оригинала, если клин отсутствует)."""
    return _h.get_page_clean_image(page_id)


@router.get("/{page_id}/blocks")
def get_page_blocks(page_id: int):
    """Получение всех текстовых баблов страницы в порядке чтения."""
    return _h.get_page_blocks(page_id)


@router.post("/{page_id}/blocks")
@router.put("/{page_id}/blocks")
def save_page_blocks_endpoint(page_id: int, req: SavePageBlocksRequest):
    """Сохранение/обновление всех баблов страницы."""
    return _h.save_page_blocks_endpoint(page_id, req)


@router.post("/{page_id}/detect")
def detect_page_bubbles_by_id(
    page_id: int,
    conf: Optional[float] = Query(None),
    auto_oval: Optional[bool] = Query(None)
):
    """Запуск автодетекции баблов (YOLO) и распознавания текста (MangaOCR)."""
    return _h.detect_page_bubbles_by_id(page_id, conf, auto_oval)


@router.post("/{page_id}/clean")
def clean_page_bubbles(page_id: int, mode: str = Query("auto")):
    """Пакетный клин всех размеченных баблов страницы (Auto / White / LaMa)."""
    return _h.clean_page_bubbles(page_id, mode)


@router.delete("/{page_id}/clean")
def revert_page_clean(page_id: int):
    """Полный откат клина страницы к исходному скану."""
    return _h.revert_page_clean(page_id)


@router.post("/{page_id}/undo-clean")
def undo_last_clean_step(page_id: int):
    """Откат последнего шага клина (Spot Clean / Brush Clean) из резервной копии."""
    return _h.undo_last_clean_step(page_id)


@router.post("/{page_id}/clean-spot")
def spot_clean_page(page_id: int, req: SpotCleanRequest):
    """Точечная очистка выделенной области страницы (Spot Clean)."""
    return _h.spot_clean_page(page_id, req)


@router.post("/{page_id}/clean-brush")
def brush_clean_page(page_id: int, req: BrushCleanRequest):
    """Очистка произвольного мазка кисти пользователя (LaMa / White / Black)."""
    return _h.brush_clean_page(page_id, req)


@router.post("/{page_id}/save-translated")
def save_translated_page(page_id: int, file: UploadFile = File(...)):
    """Сохранение готовой запечённой страницы в папку translated."""
    return _h.save_translated_page(page_id, file)


@router.post("/{page_id}/open-folder")
def open_translated_folder(page_id: int):
    """Открытие папки translated в Проводнике Windows."""
    return _h.open_translated_folder(page_id)

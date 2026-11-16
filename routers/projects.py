# routers/projects.py
"""
Роутер проектов манги (сканирование, настройки тайтлов, спикеры, глоссарий, расширенная статистика).
"""

from typing import Optional
from fastapi import APIRouter, Query

from schemas import (
    ScanProjectRequest,
    AddChapterRequest,
    GlossaryItemCreate,
    UpdateTitleSettingsRequest,
)
from routers import projects_handlers as _h

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.get("/global-settings")
def get_global_settings_endpoint():
    """Получить глобальные настройки приложения."""
    return _h.get_global_settings_endpoint()


@router.put("/global-settings")
def update_global_settings_endpoint(req: UpdateTitleSettingsRequest):
    """Обновить глобальные настройки приложения."""
    return _h.update_global_settings_endpoint(req)


@router.post("/scan")
def scan_project(req: ScanProjectRequest):
    """Первичное сканирование корневой папки тайтла со всеми главами."""
    return _h.scan_project(req)


@router.post("/{title_id}/rescan")
def rescan_project(title_id: int):
    """Повторное сканирование папки тайтла с добавлением новых глав."""
    return _h.rescan_project(title_id)


@router.post("/{title_id}/chapters")
def add_chapters_to_title(title_id: int, req: AddChapterRequest):
    """Добавить отдельную главу в тайтл."""
    return _h.add_chapters_to_title(title_id, req)


@router.get("")
def get_projects():
    """Получить список всех тайтлов."""
    return _h.get_projects()


@router.get("/detectors")
def get_available_detectors_endpoint():
    """Список доступных моделей детекции (YOLO)."""
    return _h.get_available_detectors_endpoint()


@router.get("/cleaners")
def get_available_cleaners_endpoint():
    """Список доступных моделей клина (LaMa)."""
    return _h.get_available_cleaners_endpoint()


@router.get("/ocr-models")
def get_available_ocr_models_endpoint():
    """Список доступных моделей распознавания текста (OCR)."""
    return _h.get_available_ocr_models_endpoint()


@router.get("/{title_id}/tree")
def get_project_tree(title_id: int):
    """Дерево проекта: главы, страницы и статусы."""
    return _h.get_project_tree(title_id)


@router.put("/{title_id}/settings")
def update_title_settings(title_id: int, req: UpdateTitleSettingsRequest):
    """Обновить описание/синопсис и базовый размер шрифта тайтла."""
    return _h.update_title_settings(title_id, req)


@router.get("/{title_id}/speakers")
def get_title_speakers(title_id: int, chapter_id: Optional[int] = Query(None)):
    """Список уникальных спикеров тайтла/главы."""
    return _h.get_title_speakers(title_id, chapter_id)


@router.delete("/{title_id}")
def delete_project(title_id: int):
    """Удалить тайтл и все связанные данные из базы."""
    return _h.delete_project(title_id)


@router.get("/{title_id}/glossary")
def get_glossary(title_id: int):
    """Получить термины глоссария тайтла."""
    return _h.get_glossary(title_id)


@router.post("/{title_id}/glossary")
def add_glossary_item(title_id: int, req: GlossaryItemCreate):
    """Добавить новый термин или персонажа в глоссарий."""
    return _h.add_glossary_item(title_id, req)


@router.delete("/{title_id}/glossary/{entry_id}")
def delete_glossary_item(title_id: int, entry_id: int):
    """Удалить термин из глоссария."""
    return _h.delete_glossary_item(title_id, entry_id)


# ---- Расширенная статистика по тайтлам и главам ----

@router.get("/all-detailed-stats")
def get_all_detailed_stats():
    """Детальная статистика по всем тайтлам и каждой их главе (страницы, реплики, слова, время)."""
    return _h.get_all_detailed_stats()


@router.post("/{title_id}/recalculate-all")
def recalculate_title_stats(title_id: int):
    """Пересчитать реплики и слова во всех главах выбранного тайтла."""
    return _h.recalculate_title_stats(title_id)

# routers/chapters.py
"""
Роутер глав манги (удаление, перевод главы, экспорт/импорт скриптов, управление шрифтами, таймер и статистика).
"""

from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import Response
from routers import chapters_handlers as _h

router = APIRouter(prefix="/api/chapters", tags=["Chapters"])


@router.delete("/{chapter_id}")
def delete_chapter(chapter_id: int):
    """Удаляет главу и все связанные страницы и баблы."""
    return _h.delete_chapter(chapter_id)


@router.post("/{chapter_id}/translate")
def translate_chapter(chapter_id: int):
    """Пакетный перевод всех реплик главы (или авто-импорт при наличии файла диалогов)."""
    return _h.translate_chapter_endpoint(chapter_id)


@router.post("/{chapter_id}/reset-fonts")
def reset_chapter_fonts(chapter_id: int):
    """Сбрасывает размеры всех баблов главы в Auto (font_size = NULL)."""
    return _h.reset_chapter_fonts(chapter_id)


@router.post("/{chapter_id}/apply-font-size")
def apply_chapter_font_size(chapter_id: int, font_size: int = Query(...)):
    """Применяет конкретный размер кегля ко всем баблам всех страниц главы."""
    return _h.apply_chapter_font_size(chapter_id, font_size)


@router.get("/{chapter_id}/export-dialogue")
def export_chapter_dialogue(chapter_id: int) -> Response:
    """Скачивание чистого JSON файла диалогов в браузере."""
    return _h.export_chapter_dialogue(chapter_id)


@router.post("/{chapter_id}/export-dialogue-to-folder")
def export_chapter_dialogue_to_folder_endpoint(chapter_id: int):
    """Сохраняет оба файла (_context.json и _dialogues.json) прямо в папку главы на диске."""
    return _h.export_chapter_dialogue_to_folder_endpoint(chapter_id)


@router.post("/{chapter_id}/import-dialogue")
async def import_chapter_dialogue(chapter_id: int, file: UploadFile = File(...)):
    """Импортирует JSON с переводом, переданный файлом через форму."""
    return await _h.import_chapter_dialogue(chapter_id, file)


@router.post("/{chapter_id}/pick-and-import-dialogue")
def pick_and_import_dialogue_endpoint(chapter_id: int):
    """Автоматически находит файл диалогов в папке главы или возвращает флаг для открытия браузерного выбора файла."""
    return _h.pick_and_import_dialogue_endpoint(chapter_id)


@router.post("/{chapter_id}/import-dialogue-from-folder")
def import_dialogue_from_folder_endpoint(chapter_id: int):
    """Автоматически находит последний JSON файл диалогов в папке главы и импортирует его."""
    return _h.import_dialogue_from_folder_endpoint(chapter_id)


# ---- Таймер и подсчёт реплик/слов главы ----

@router.get("/{chapter_id}/timer/status")
def get_chapter_timer_status(chapter_id: int):
    """Получить статус таймера главы и общее затраченное время."""
    return _h.get_chapter_timer_status(chapter_id)


@router.post("/{chapter_id}/timer/start")
def start_chapter_timer(chapter_id: int):
    """Запустить таймер работы над текущей главой."""
    return _h.start_chapter_timer(chapter_id)


@router.post("/{chapter_id}/timer/stop")
def stop_chapter_timer(chapter_id: int):
    """Остановить таймер работы над текущей главой и зафиксировать время."""
    return _h.stop_chapter_timer(chapter_id)


@router.post("/{chapter_id}/recalculate-stats")
def recalculate_chapter_stats(chapter_id: int):
    """Принудительно пересчитать количество переведённых реплик и русских слов главы."""
    return _h.recalculate_chapter_stats(chapter_id)

import os
import sys
import shutil
import subprocess
from PIL import Image
from fastapi import HTTPException, UploadFile
from database import get_db, db_session
from services.page_service_ops.active_settings import get_active_global_settings
from logger import logger

# Поддерживаемые форматы запечённых страниц
EXPORT_FORMATS = ("png", "webp", "avif")

# Параметры сохранения сжатых форматов (PNG пишется как есть из Canvas-блоба)
EXPORT_SAVE_OPTIONS = {
    "webp": {"format": "WEBP", "quality": 95, "method": 6},
    "avif": {"format": "AVIF", "quality": 92},
}


def save_translated_page(page_id: int, file: UploadFile):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM pages WHERE id = ?", (page_id,))
        page_row = cursor.fetchone()

    if not page_row:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    orig_path = page_row["file_path"]
    translated_dir = os.path.join(os.path.dirname(orig_path), "translated")
    os.makedirs(translated_dir, exist_ok=True)

    cfg = get_active_global_settings()
    export_format = (cfg.get("export_format") or "png").lower()
    if export_format not in EXPORT_FORMATS:
        export_format = "png"

    file_name = os.path.splitext(os.path.basename(orig_path))[0]
    final_path = os.path.join(translated_dir, f"{file_name}.{export_format}")

    try:
        if export_format == "png":
            # Фронтенд присылает PNG-блоб из Canvas — сохраняем байт-в-байт
            with open(final_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        else:
            with Image.open(file.file) as img:
                img.convert("RGB").save(final_path, **EXPORT_SAVE_OPTIONS[export_format])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось сохранить файл: {e}")

    # Удаляем старые версии этой же страницы в других форматах,
    # чтобы в translated/ не дублировались страницы (например, 01.png и 01.webp).
    for ext in EXPORT_FORMATS:
        if ext == export_format:
            continue
        stale_path = os.path.join(translated_dir, f"{file_name}.{ext}")
        try:
            if os.path.exists(stale_path):
                os.remove(stale_path)
        except OSError as e:
            logger.warning(f"Не удалось удалить старый файл страницы {stale_path}: {e}")

    with db_session() as cur:
        cur.execute("UPDATE pages SET status = 'done' WHERE id = ?", (page_id,))

    return {"success": True, "saved_path": final_path, "page_status": "done"}


def open_translated_folder(page_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM pages WHERE id = ?", (page_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    translated_dir = os.path.join(os.path.dirname(row["file_path"]), "translated")
    os.makedirs(translated_dir, exist_ok=True)

    try:
        if hasattr(os, "startfile"):
            os.startfile(translated_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", translated_dir])
        else:
            subprocess.Popen(["xdg-open", translated_dir])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось открыть папку в проводнике: {e}")

    return {"success": True}

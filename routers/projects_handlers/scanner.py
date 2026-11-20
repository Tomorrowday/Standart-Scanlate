import os
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Set
from fastapi import HTTPException

from database import db_session, get_db
from schemas import ScanProjectRequest, AddChapterRequest
from config import natural_sort_key
from logger import logger

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".jfif", ".avif"}
EXCLUDED_DIR_NAMES = {
    "clean", "cleaned", "translated", "export", "exports",
    "raw", ".git", ".idea", "__pycache__", "logs"
}


def _has_image_subdirs(root_folder: Path) -> bool:
    """Проверяет, есть ли внутри root_folder подпапки с изображениями (главами)."""
    norm_root = os.path.normpath(str(root_folder)).lower()
    for root, dirs, files in os.walk(root_folder):
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDED_DIR_NAMES]
        if os.path.normpath(root).lower() == norm_root:
            continue
        if any(Path(f).suffix.lower() in VALID_IMAGE_EXTENSIONS for f in files):
            return True
    return False


def _scan_and_insert_chapters(
    cur: sqlite3.Cursor,
    title_id: int,
    root_folder: Path,
    skip_existing: bool = False,
    existing_folders: Optional[Set[str]] = None,
    existing_names: Optional[Set[str]] = None,
    custom_chapter_name: Optional[str] = None
) -> Tuple[int, int, int]:
    added_chapters = 0
    added_pages = 0
    skipped_chapters = 0

    existing_folders = existing_folders or set()
    existing_names = existing_names or set()

    direct_files = [f for f in os.listdir(root_folder) if (root_folder / f).is_file()]
    direct_images = [f for f in direct_files if Path(f).suffix.lower() in VALID_IMAGE_EXTENSIONS]

    # Если в корне лежит обложка, но есть подпапки с главами и сканируется
    # весь тайтл (не задана конкретная глава) — не создаём главу из обложки.
    skip_root_direct = False
    if direct_images and not (custom_chapter_name and custom_chapter_name.strip()):
        skip_root_direct = _has_image_subdirs(root_folder)

    if direct_images and not skip_root_direct:
        norm_root = os.path.normcase(os.path.abspath(str(root_folder)))
        ch_name = (
            custom_chapter_name.strip()
            if custom_chapter_name and custom_chapter_name.strip()
            else root_folder.name
        )

        if skip_existing and (norm_root in existing_folders or ch_name.lower() in existing_names):
            return 0, 0, 1

        direct_images.sort(key=natural_sort_key)
        cur.execute(
            "INSERT INTO chapters (title_id, chapter_number, folder_path) VALUES (?, ?, ?)",
            (title_id, ch_name, str(root_folder))
        )
        chapter_id = cur.lastrowid
        added_chapters += 1

        for i, img in enumerate(direct_images):
            cur.execute(
                "INSERT INTO pages (chapter_id, page_number, file_path) VALUES (?, ?, ?)",
                (chapter_id, i + 1, str(root_folder / img))
            )
            added_pages += 1

        return added_chapters, added_pages, skipped_chapters

    walk_dirs = []
    for root, dirs, files in os.walk(root_folder):
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDED_DIR_NAMES]
        walk_dirs.append((root, dirs, files))

    walk_dirs.sort(key=lambda item: natural_sort_key(item[0]))

    for root, _, files in walk_dirs:
        if Path(root).name.lower() in EXCLUDED_DIR_NAMES:
            continue

        if skip_root_direct and os.path.normpath(root).lower() == os.path.normpath(str(root_folder)).lower():
            # Одиночные картинки в корне (обложка) не должны становиться главой
            continue

        images = [f for f in files if Path(f).suffix.lower() in VALID_IMAGE_EXTENSIONS]
        if not images:
            continue

        norm_root = os.path.normcase(os.path.abspath(root))
        chapter_name = Path(root).name

        if skip_existing and (norm_root in existing_folders or chapter_name.strip().lower() in existing_names):
            skipped_chapters += 1
            continue

        images.sort(key=natural_sort_key)
        cur.execute(
            "INSERT INTO chapters (title_id, chapter_number, folder_path) VALUES (?, ?, ?)",
            (title_id, chapter_name, root)
        )
        chapter_id = cur.lastrowid
        added_chapters += 1

        for i, img in enumerate(images):
            cur.execute(
                "INSERT INTO pages (chapter_id, page_number, file_path) VALUES (?, ?, ?)",
                (chapter_id, i + 1, os.path.join(root, img))
            )
            added_pages += 1

    return added_chapters, added_pages, skipped_chapters


def scan_project(req: ScanProjectRequest):
    folder = Path(req.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Папка не найдена или путь указан неверно")

    try:
        with db_session() as cursor:
            cursor.execute(
                "INSERT INTO titles (name, folder_path, default_font_size) VALUES (?, ?, 14)",
                (req.name, str(folder))
            )
            title_id = cursor.lastrowid

            chapters_count, pages_count, _ = _scan_and_insert_chapters(
                cursor, title_id=title_id, root_folder=folder, skip_existing=False
            )

        logger.info(f"Отсканирован проект '{req.name}': {chapters_count} глав, {pages_count} страниц.")
        return {
            "success": True,
            "message": f"Тайтл '{req.name}' добавлен! Глав: {chapters_count}, страниц: {pages_count}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка сканирования папки: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def rescan_project(title_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, folder_path FROM titles WHERE id = ?", (title_id,))
        title_row = cursor.fetchone()

        if not title_row:
            raise HTTPException(status_code=404, detail="Тайтл не найден")

        folder = Path(title_row["folder_path"])
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail=f"Корневая папка тайтла не найдена: {folder}")

        cursor.execute("SELECT chapter_number, folder_path FROM chapters WHERE title_id = ?", (title_id,))
        existing_rows = cursor.fetchall()

    existing_folders = {
        os.path.normcase(os.path.abspath(r["folder_path"]))
        for r in existing_rows
        if r["folder_path"]
    }
    # Имена сравниваем только для legacy-строк без folder_path: иначе «Ch1» из
    # Vol1 и Vol2 считались бы одной главой.
    existing_names = {
        r["chapter_number"].strip().lower()
        for r in existing_rows
        if not r["folder_path"] and r["chapter_number"]
    }

    try:
        with db_session() as cur:
            added_chapters, added_pages, skipped_chapters = _scan_and_insert_chapters(
                cur,
                title_id=title_id,
                root_folder=folder,
                skip_existing=True,
                existing_folders=existing_folders,
                existing_names=existing_names
            )

        return {
            "success": True,
            "message": f"Скан завершён. Добавлено: {added_chapters} глав. Пропущено: {skipped_chapters}.",
            "added_chapters": added_chapters,
            "added_pages": added_pages,
            "skipped_chapters": skipped_chapters,
        }
    except Exception as e:
        logger.error(f"Ошибка рескана проекта {title_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def add_chapters_to_title(title_id: int, req: AddChapterRequest):
    folder = Path(req.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Папка не найдена или путь некорректен")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM titles WHERE id = ?", (title_id,))
        title_row = cursor.fetchone()
        cursor.execute("SELECT chapter_number, folder_path FROM chapters WHERE title_id = ?", (title_id,))
        existing_rows = cursor.fetchall()

    if not title_row:
        raise HTTPException(status_code=404, detail="Тайтл не найден")

    existing_folders = {
        os.path.normcase(os.path.abspath(r["folder_path"]))
        for r in existing_rows
        if r["folder_path"]
    }
    existing_names = {
        r["chapter_number"].strip().lower()
        for r in existing_rows
        if not r["folder_path"] and r["chapter_number"]
    }

    try:
        with db_session() as cur:
            added_chapters, added_pages, skipped_chapters = _scan_and_insert_chapters(
                cur,
                title_id=title_id,
                root_folder=folder,
                skip_existing=True,
                existing_folders=existing_folders,
                existing_names=existing_names,
                custom_chapter_name=req.chapter_number
            )

        if added_chapters == 0:
            if skipped_chapters > 0:
                return {
                    "success": True,
                    "message": f"Глава уже добавлена ранее (пропущено: {skipped_chapters})",
                    "chapters_added": 0,
                    "pages_added": 0,
                    "skipped_chapters": skipped_chapters,
                }
            raise HTTPException(status_code=400, detail="В папке не найдено изображений")

        return {
            "success": True,
            "message": f"Добавлено глав: {added_chapters}, страниц: {added_pages}",
            "chapters_added": added_chapters,
            "pages_added": added_pages,
            "skipped_chapters": skipped_chapters,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка добавления главы в тайтл {title_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import os
import shutil
import mimetypes
import threading
from pathlib import Path
from typing import Optional, List
from fastapi import HTTPException
from fastapi.responses import Response, FileResponse

MAX_CLEAN_BACKUPS = 1

# Блокировки клина по странице: два параллельных запроса spot_clean/brush_clean
# к одной странице не должны одновременно читать и перезаписывать clean/*.png.
# ВАЖНО: lock действует в пределах одного процесса. При запуске uvicorn с
# несколькими воркерами нужен файловый lock (сейчас приложение работает в
# одном процессе, см. docs/architecture-decisions.md).
_page_clean_locks: dict[int, threading.Lock] = {}
_page_clean_locks_guard = threading.Lock()


def page_clean_lock(page_id: int) -> threading.Lock:
    """Возвращает per-page блокировку операций клина (чтение-клин-запись)."""
    with _page_clean_locks_guard:
        return _page_clean_locks.setdefault(page_id, threading.Lock())


def _get_clean_backup_path(orig_path: str) -> str:
    """Путь одиночного легаси-бэкапа (для обратной совместимости)."""
    clean_dir = os.path.join(os.path.dirname(orig_path), "clean")
    os.makedirs(clean_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(orig_path))[0]
    return os.path.join(clean_dir, f"{base_name}_undo_backup.png")


def _list_clean_backups(orig_path: str) -> List[str]:
    """Возвращает отсортированный по возрастанию список существующих шагов бэкапа клина."""
    clean_dir = os.path.join(os.path.dirname(orig_path), "clean")
    if not os.path.exists(clean_dir):
        return []
    base_name = os.path.splitext(os.path.basename(orig_path))[0]
    prefix = f"{base_name}_undo_backup_"
    items = []
    for fname in os.listdir(clean_dir):
        if fname.startswith(prefix) and fname.endswith(".png"):
            idx_str = fname[len(prefix):-4]
            if idx_str.isdigit():
                items.append((int(idx_str), os.path.join(clean_dir, fname)))
    items.sort(key=lambda x: x[0])
    paths = [p for _, p in items]

    legacy = _get_clean_backup_path(orig_path)
    if os.path.exists(legacy):
        paths.insert(0, legacy)
    return paths


def _clear_clean_backups(orig_path: str) -> None:
    """Удаляет все файлы бэкапов клина для данной страницы."""
    for p in _list_clean_backups(orig_path):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def cleanup_other_pages_clean_backups(current_orig_path: str) -> None:
    """Удаляет все файлы *_undo_backup*.png в папке clean/, кроме текущей открытой страницы."""
    if not current_orig_path:
        return
    clean_dir = os.path.join(os.path.dirname(current_orig_path), "clean")
    if not os.path.exists(clean_dir):
        return

    current_base = os.path.splitext(os.path.basename(current_orig_path))[0]
    keep_prefixes = (f"{current_base}_undo_backup_", f"{current_base}_undo_backup.png")

    for fname in os.listdir(clean_dir):
        if "_undo_backup" in fname and fname.endswith(".png"):
            if not fname.startswith(keep_prefixes):
                try:
                    os.remove(os.path.join(clean_dir, fname))
                except Exception:
                    pass


def _backup_clean_file_if_exists(orig_path: str, clean_path: Optional[str]) -> None:
    """Сохраняет текущее состояние заклиненного скана в стек бэкапов (не более MAX_CLEAN_BACKUPS = 1)."""
    if not clean_path or not os.path.exists(clean_path):
        return

    clean_dir = os.path.join(os.path.dirname(orig_path), "clean")
    os.makedirs(clean_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(orig_path))[0]
    prefix = f"{base_name}_undo_backup_"

    existing = _list_clean_backups(orig_path)
    while len(existing) >= MAX_CLEAN_BACKUPS:
        oldest = existing.pop(0)
        try:
            os.remove(oldest)
        except Exception:
            pass

    target_backup = os.path.join(clean_dir, f"{prefix}001.png")
    try:
        shutil.copy2(clean_path, target_backup)
    except Exception:
        pass


def serve_image_file_safely(file_path: str, no_cache: bool = False) -> Response:
    """
    Отдаёт изображение страницы через FileResponse (стриминг, ETag, Last-Modified).

    no_cache=True нужен для clean-image: после кисти/точечного клина браузер не
    должен показывать старый заклиненный скан из кэша.
    """
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл изображения не найден на диске")

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "image/png" if file_path.lower().endswith(".png") else "image/jpeg"

    cache_control = "no-cache" if no_cache else "public, max-age=3600"
    return FileResponse(
        path=file_path,
        media_type=mime_type,
        headers={"Cache-Control": cache_control},
    )

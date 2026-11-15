import os
import shutil
import mimetypes
from pathlib import Path
from typing import Optional, List
from fastapi import HTTPException
from fastapi.responses import Response

MAX_CLEAN_BACKUPS = 15


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


def _backup_clean_file_if_exists(orig_path: str, clean_path: Optional[str]) -> None:
    """Сохраняет текущее состояние заклиненного скана в стек бэкапов (до MAX_CLEAN_BACKUPS шагов)."""
    if not clean_path or not os.path.exists(clean_path):
        return

    clean_dir = os.path.join(os.path.dirname(orig_path), "clean")
    os.makedirs(clean_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(orig_path))[0]
    prefix = f"{base_name}_undo_backup_"

    existing = _list_clean_backups(orig_path)
    # Если превышен лимит — удаляем самый старый шаг
    while len(existing) >= MAX_CLEAN_BACKUPS:
        oldest = existing.pop(0)
        try:
            os.remove(oldest)
        except Exception:
            pass

    next_idx = 1
    for p in existing:
        fname = os.path.basename(p)
        if fname.startswith(prefix) and fname.endswith(".png"):
            num_str = fname[len(prefix):-4]
            if num_str.isdigit():
                next_idx = max(next_idx, int(num_str) + 1)

    target_backup = os.path.join(clean_dir, f"{prefix}{next_idx:03d}.png")
    try:
        shutil.copy2(clean_path, target_backup)
    except Exception:
        pass


def serve_image_file_safely(file_path: str) -> Response:
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл изображения не найден на диске")

    try:
        data = Path(file_path).read_bytes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось прочитать файл: {e}")

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "image/png" if file_path.lower().endswith(".png") else "image/jpeg"

    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Content-Length": str(len(data)),
            "Cache-Control": "public, max-age=3600",
        }
    )

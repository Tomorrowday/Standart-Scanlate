import os
import shutil
import time
from fastapi import HTTPException
from database import get_db
from routers.pages_handlers.common import (
    _backup_clean_file_if_exists,
    _list_clean_backups,
    _clear_clean_backups,
)
from services.page_service import clean_page_bubbles_service, revert_page_clean_service


def clean_page_bubbles(page_id: int, mode: str = "auto"):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT file_path, clean_path FROM pages WHERE id = ?", (page_id,))
            row = cur.fetchone()
            if row:
                _backup_clean_file_if_exists(str(row["file_path"]), row["clean_path"])

        clean_path, new_status, stats = clean_page_bubbles_service(page_id, clean_mode=mode)
        return {
            "success": True,
            "clean_path": clean_path,
            "page_status": new_status,
            "whitened": stats["white"],
            "inpainted": stats["inpaint"]
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def revert_page_clean(page_id: int):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT file_path FROM pages WHERE id = ?", (page_id,))
            row = cur.fetchone()
            if row and row["file_path"]:
                _clear_clean_backups(str(row["file_path"]))

        new_status = revert_page_clean_service(page_id)
        return {"success": True, "page_status": new_status, "message": "Клин страницы успешно откачен"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def undo_last_clean_step(page_id: int):
    """Откатывает последний шаг клина из стека резервных копий без удаления всего клина страницы."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT file_path, clean_path, status FROM pages WHERE id = ?", (page_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    orig_path = str(row["file_path"])
    clean_path = str(row["clean_path"]) if row["clean_path"] else ""
    backups = _list_clean_backups(orig_path)

    if backups and clean_path:
        latest_backup = backups[-1]
        try:
            shutil.copy2(latest_backup, clean_path)
            os.remove(latest_backup)
            return {
                "success": True,
                "restored_from_backup": True,
                "clean_path": clean_path,
                "page_status": row["status"],
                "timestamp": int(time.time() * 1000),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка восстановления бэкапа клина: {e}")

    # Если бэкапов больше нет — НЕ удаляем весь clean_path страницы,
    # чтобы повторный Ctrl+Z не уничтожил результат предыдущей работы
    return {
        "success": False,
        "restored_from_backup": False,
        "clean_path": clean_path or None,
        "page_status": row["status"],
        "error": "Нет сохранённых шагов клина для отката",
    }

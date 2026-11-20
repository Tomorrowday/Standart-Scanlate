import os
import time
from fastapi import HTTPException
from database import get_db, db_session
from schemas import SpotCleanRequest
from routers.pages_handlers.common import _backup_clean_file_if_exists, page_clean_lock
from services.cleaner import spot_clean_region, load_image_cv2, save_image_cv2, release_vram
from services.page_service import get_active_global_settings
from services.page_service_ops.page_status import resolve_clean_status


def spot_clean_page(page_id: int, req: SpotCleanRequest):
    # Сериализуем клин одной страницы (чтение clean/*.png -> инпейнт -> запись).
    with page_clean_lock(page_id):
        return _spot_clean_page_locked(page_id, req)


def _spot_clean_page_locked(page_id: int, req: SpotCleanRequest):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.file_path, p.clean_path, p.status
            FROM pages p
            WHERE p.id = ?
            """,
            (page_id,)
        )
        page_row = cursor.fetchone()

    if not page_row:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    orig_path = str(page_row["file_path"])
    existing_clean = str(page_row["clean_path"]) if page_row["clean_path"] and os.path.exists(page_row["clean_path"]) else None
    _backup_clean_file_if_exists(orig_path, existing_clean)

    source_path = existing_clean if existing_clean else orig_path

    if not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail="Исходный файл страницы не найден")

    try:
        image = load_image_cv2(source_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось открыть изображение: {e}")

    box_dict = {
        "x": req.x,
        "y": req.y,
        "width": req.width,
        "height": req.height,
        "rotation": req.rotation or 0.0,
        "shape": req.shape or "rect",
        "class_id": req.class_id if req.class_id is not None else 0,
    }
    cfg = get_active_global_settings()
    clean_model_name = cfg.get("clean_model") or "anime-manga-big-lama.pt"
    downscale = bool(cfg.get("lama_downscale", 0))
    brush_model = str(cfg.get("brush_model") or "opencv")
    brush_threshold = float(cfg.get("brush_threshold") or 0.5)
    brush_extra_dilate = int(cfg.get("brush_extra_dilate") or 0)
    brush_max_side = int(cfg.get("brush_max_side") or 512)

    try:
        used_method = spot_clean_region(
            image, box_dict,
            method=req.method or "auto",
            clean_model_name=clean_model_name,
            brush_model=brush_model,
            brush_threshold=brush_threshold,
            brush_extra_dilate=brush_extra_dilate,
            brush_max_side=brush_max_side,
            downscale=downscale,
        )
    finally:
        release_vram()

    clean_dir = os.path.join(os.path.dirname(orig_path), "clean")
    os.makedirs(clean_dir, exist_ok=True)
    final_clean_path = str(os.path.join(clean_dir, f"{os.path.splitext(os.path.basename(orig_path))[0]}.png"))

    if not save_image_cv2(final_clean_path, image):
        raise HTTPException(status_code=500, detail="Не удалось сохранить заклиненный файл")

    new_status = resolve_clean_status(page_row["status"])

    with db_session() as cur:
        cur.execute("UPDATE pages SET clean_path = ?, status = ? WHERE id = ?", (final_clean_path, new_status, page_id))

    return {
        "success": True,
        "clean_path": final_clean_path,
        "page_status": new_status,
        "method": used_method,
        "timestamp": int(time.time() * 1000)
    }

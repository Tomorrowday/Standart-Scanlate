import os
import time
import base64
import cv2
import numpy as np
from fastapi import HTTPException
from database import get_db, db_session
from schemas.blocks import BrushCleanRequest
from routers.pages_handlers.common import _backup_clean_file_if_exists, page_clean_lock
from services.cleaner import inpaint_by_brush_mask, load_image_cv2, save_image_cv2, release_vram
from services.page_service import get_active_global_settings
from services.page_service_ops.page_status import resolve_clean_status


def brush_clean_page(page_id: int, req: BrushCleanRequest):
    # Сериализуем клин одной страницы (чтение clean/*.png -> инпейнт -> запись).
    with page_clean_lock(page_id):
        return _brush_clean_page_locked(page_id, req)


def _brush_clean_page_locked(page_id: int, req: BrushCleanRequest):
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

    try:
        image = load_image_cv2(source_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось открыть изображение: {e}")

    try:
        raw_b64 = req.mask_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        mask_bytes = base64.b64decode(raw_b64)
        mask_arr = np.frombuffer(mask_bytes, dtype=np.uint8)
        mask_img = cv2.imdecode(mask_arr, cv2.IMREAD_GRAYSCALE)

        if mask_img is None:
            raise ValueError("Не удалось декодировать маску")

        if req.mask_rect is not None:
            # Пришёл только кроп мазка — вставляем его в полноразмерную маску.
            rect = req.mask_rect
            img_h, img_w = image.shape[:2]
            rx = max(0, int(rect.x))
            ry = max(0, int(rect.y))
            rw = max(1, int(rect.width))
            rh = max(1, int(rect.height))

            rx2 = min(img_w, rx + rw)
            ry2 = min(img_h, ry + rh)
            if rx2 <= rx or ry2 <= ry:
                raise ValueError("Кроп маски вне границ изображения")

            crop_w, crop_h = rx2 - rx, ry2 - ry
            if mask_img.shape[:2] != (crop_h, crop_w):
                mask_img = cv2.resize(mask_img, (crop_w, crop_h), interpolation=cv2.INTER_NEAREST)

            full_mask = np.zeros((img_h, img_w), dtype=np.uint8)
            full_mask[ry:ry2, rx:rx2] = mask_img
            mask_img = full_mask
        elif mask_img.shape[:2] != image.shape[:2]:
            # Совместимость со старым клиентом: маска на всю страницу.
            mask_img = cv2.resize(mask_img, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка обработки маски: {e}")

    cfg = get_active_global_settings()
    clean_model_name = cfg.get("clean_model") or "anime-manga-big-lama.pt"
    downscale = bool(cfg.get("lama_downscale", 0))

    try:
        inpaint_by_brush_mask(
            image, mask_img,
            mode=req.mode or "lama",
            clean_model_name=clean_model_name,
            downscale=downscale,
        )
    finally:
        release_vram()

    clean_dir = os.path.join(os.path.dirname(orig_path), "clean")
    os.makedirs(clean_dir, exist_ok=True)
    file_name = os.path.splitext(os.path.basename(orig_path))[0]
    final_clean_path = str(os.path.join(clean_dir, f"{file_name}.png"))

    if not save_image_cv2(final_clean_path, image):
        raise HTTPException(status_code=500, detail="Не удалось сохранить заклиненный файл")

    new_status = resolve_clean_status(page_row["status"])

    with db_session() as cur:
        cur.execute("UPDATE pages SET clean_path = ?, status = ? WHERE id = ?", (final_clean_path, new_status, page_id))

    return {
        "success": True,
        "clean_path": final_clean_path,
        "page_status": new_status,
        "timestamp": int(time.time() * 1000)
    }

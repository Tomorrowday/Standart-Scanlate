# routers/ai_impl.py
# Реализация эндпоинтов AI (MangaOCR распознавание с кэшем последнего изображения страницы)

import os
import threading
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

from database import get_db
from schemas import OcrRequest
from services.ocr import ocr_image_region

_ocr_cache_lock = threading.Lock()
_cached_page_image: Tuple[Optional[int], Optional[float], Optional[Image.Image]] = (None, None, None)


def _get_cached_page_image(page_id: int, file_path: str) -> Image.Image:
    """Возвращает PIL.Image из кэша, если страница и mtime файла не изменились."""
    global _cached_page_image
    mtime = os.path.getmtime(file_path)

    with _ocr_cache_lock:
        c_id, c_mtime, c_img = _cached_page_image
        if c_id == page_id and c_mtime == mtime and c_img is not None:
            return c_img

    img = Image.open(file_path).convert("RGB")
    with _ocr_cache_lock:
        _cached_page_image = (page_id, mtime, img)
    return img


def perform_ocr(req: OcrRequest):
    """Распознавание японского текста (MangaOCR) по координатам с учётом угла поворота."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM pages WHERE id = ?", (req.page_id,))
            row = cursor.fetchone()

            if not row or not os.path.exists(row["file_path"]):
                return {"success": False, "error": "Файл страницы не найден"}

            # Читаем блоки страницы, чтобы передать OCR соседние рамки (маскирование чужого текста)
            cursor.execute(
                "SELECT id, x, y, width, height, class_id FROM text_blocks WHERE page_id = ?",
                (req.page_id,),
            )
            block_rows = cursor.fetchall()

        # Текущий блок ищем сначала по id от клиента, затем по совпадению координат (точность 1e-3)
        blocks: List[Dict[str, Any]] = [
            {
                "id": str(block["id"]),
                "x": float(block["x"]),
                "y": float(block["y"]),
                "width": float(block["width"]),
                "height": float(block["height"]),
                "class_id": int(block["class_id"] or 0),
            }
            for block in block_rows
        ]

        def _is_same_block(block: Dict[str, Any]) -> bool:
            return (
                abs(block["x"] - req.x) <= 1e-3
                and abs(block["y"] - req.y) <= 1e-3
                and abs(block["width"] - req.width) <= 1e-3
                and abs(block["height"] - req.height) <= 1e-3
            )

        # 1. Приоритет — точный block_id, присланный клиентом: никакая эвристика не нужна
        current_idx: Optional[int] = None
        if req.block_id:
            current_idx = next(
                (i for i, block in enumerate(blocks) if block["id"] == str(req.block_id)),
                None,
            )

        # 2. Фолбэк — блок ещё не сохранён в БД: ищем по точному совпадению координат
        if current_idx is None:
            current_idx = next(
                (i for i, block in enumerate(blocks) if _is_same_block(block)), None
            )

        # 3. Фолбэк — рамку подвинули вручную без сохранения: узнаём блок по IoU,
        # иначе он попал бы в other_boxes и замаскировал сам себя
        if current_idx is None:
            req_x1, req_y1 = req.x, req.y
            req_x2, req_y2 = req.x + req.width, req.y + req.height
            req_area = max(1e-9, req.width * req.height)
            best_iou = 0.0
            best_idx: Optional[int] = None
            for i, block in enumerate(blocks):
                bx1, by1 = block["x"], block["y"]
                bx2, by2 = bx1 + block["width"], by1 + block["height"]
                ix1, iy1 = max(req_x1, bx1), max(req_y1, by1)
                ix2, iy2 = min(req_x2, bx2), min(req_y2, by2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                inter = (ix2 - ix1) * (iy2 - iy1)
                union = req_area + max(1e-9, block["width"] * block["height"]) - inter
                iou = inter / union
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i
            # Порог 0.45: ручной ресайз рамки перед сохранением даёт IoU ~0.55
            if best_idx is not None and best_iou >= 0.45:
                current_idx = best_idx

        if req.class_id is not None:
            current_class_id = int(req.class_id)
        else:
            current_class_id = blocks[current_idx]["class_id"] if current_idx is not None else 0
        other_boxes: List[Dict[str, Any]] = [
            block for i, block in enumerate(blocks) if i != current_idx
        ]

        image = _get_cached_page_image(req.page_id, str(row["file_path"]))
        text = ocr_image_region(
            image,
            req.x,
            req.y,
            req.width,
            req.height,
            rotation=req.rotation or 0.0,
            class_id=current_class_id,
            other_boxes=other_boxes,
        )

        return {"success": True, "text": text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def translate_text_stub():
    """Заглушка: перевод вынесен на клиент (Ollama) и в раздельный JSON-экспорт."""
    return {
        "success": False,
        "error": "Облачный перевод отключен. Используйте Export JSON для Claude/ChatGPT или локальную Ollama."
    }


def translate_batch_stub():
    """Заглушка пакетного перевода."""
    return {"success": False, "translations": {}}
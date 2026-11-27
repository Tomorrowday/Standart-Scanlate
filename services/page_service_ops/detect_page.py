# services/page_service_ops/detect_page.py
# Автодетект баблов на странице через YOLO + OCR японского текста

import os
import time
import uuid
from typing import List, Dict, Any, Tuple, Optional

from PIL import Image

from database import get_db, db_session
from services.cleaner import release_vram
from services.detector import detect_and_filter_bubbles
from services.ocr import ocr_image_region
from services.page_service_ops.active_settings import get_active_global_settings


def detect_page_bubbles_service(
    page_id: int,
    conf_override: Optional[float] = None,
    auto_oval_override: Optional[bool] = None
) -> Tuple[List[Dict[str, Any]], str, float]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, status FROM pages WHERE id = ?", (page_id,))
        row = cursor.fetchone()

    if not row or not os.path.exists(str(row["file_path"])):
        raise ValueError("Файл не найден на диске")

    file_path = str(row["file_path"])

    cfg = get_active_global_settings()
    detector_model = cfg.get("detector_model") or "yolo_manga.pt"
    ocr_model = cfg.get("ocr_model") or "manga-ocr-base"
    detect_conf = conf_override if conf_override is not None else float(cfg.get("detect_conf", 0.25))
    detect_sfx = bool(cfg.get("show_sfx", 0))

    default_pad = cfg.get("default_padding") or "safe"
    # Инверсия полярности: default_hyphenation=true означает «с переносами»,
    # а min_hyphens=1 (true) в блоке — наоборот, режим No-Hyph (без переносов).
    min_hyphens = not bool(cfg.get("default_hyphenation", 1))
    default_stroke = bool(cfg.get("default_stroke", 0))

    font_bubble = cfg.get("font_bubble") or "v_CCFaceFront"
    font_thought = cfg.get("font_thought") or "v_CCFaceFront"
    font_sfx = cfg.get("font_sfx") or "v_Mighty Zeo 2.0"

    start_time = time.time()
    try:
        image = Image.open(file_path).convert("RGB")

        raw_boxes = detect_and_filter_bubbles(
            image,
            model_name=detector_model,
            conf_threshold=float(detect_conf),
            detect_sfx=detect_sfx
        )
        boxes: List[Dict[str, Any]] = [dict(b) for b in raw_boxes]

        # Сначала собираем все метаданные и выполняем OCR ВНЕ транзакции:
        # OCR страницы занимает 5–30 секунд, и открытый write-lock SQLite на это
        # время блокирует heartbeat таймера, сохранение других страниц и глоссарий.
        rows_to_insert: List[Tuple[Any, ...]] = []
        for idx, b in enumerate(boxes):
            block_id = str(uuid.uuid4())
            cls_id = int(b.get("class_id", 0))
            block_shape = "rect"

            if cls_id == 0:
                block_font = font_bubble
            elif cls_id == 1:
                block_font = font_thought
            else:
                block_font = font_sfx

            b["id"] = block_id
            b["class_id"] = cls_id
            b["shape"] = block_shape
            b["font_family"] = block_font
            b["font_size"] = None
            b["padding_mode"] = default_pad
            b["min_hyphens"] = min_hyphens
            b["has_stroke"] = default_stroke
            b["text_color"] = "black"
            b["rotation"] = 0.0

            other_boxes = [boxes[j] for j in range(len(boxes)) if j != idx]
            jap_text = ocr_image_region(
                image,
                float(b["x"]),
                float(b["y"]),
                float(b["width"]),
                float(b["height"]),
                rotation=0.0,
                class_id=cls_id,
                other_boxes=other_boxes,
                ocr_model_name=ocr_model,
            )
            b["jap_text"] = jap_text
            b["status"] = "ocr-done" if jap_text else "new"

            rows_to_insert.append((
                block_id, page_id, cls_id, b["x"], b["y"], b["width"], b["height"], jap_text, b["order_index"],
                block_font, block_shape, default_pad, int(min_hyphens), int(default_stroke), b["status"]
            ))

        # Быстрая запись (< 2 мс): удаление старых блоков и вставка новых.
        with db_session() as cur:
            cur.execute("DELETE FROM text_blocks WHERE page_id = ?", (page_id,))
            if rows_to_insert:
                cur.executemany(
                    """
                    INSERT OR REPLACE INTO text_blocks (
                        id, page_id, class_id, x, y, width, height, rotation, jap_text, order_index, 
                        font_size, font_family, text_color, shape, padding_mode, min_hyphens, has_stroke, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, NULL, ?, 'black', ?, ?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )

            # Повторный детект удалил блоки вместе с переводом, поэтому статус
            # всегда актуализируем (в т.ч. для cleaned/translated/done).
            new_status = "detected" if boxes else "raw"
            cur.execute("UPDATE pages SET status = ? WHERE id = ?", (new_status, page_id))

        elapsed = round(time.time() - start_time, 4)
        return boxes, new_status, elapsed
    finally:
        release_vram()

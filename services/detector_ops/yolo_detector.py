# services/detector_ops/yolo_detector.py
# Вызов YOLO, фильтрация вложенных рамок и сборка результата детекции

from typing import List, Dict, Any, Tuple
from collections import Counter
import cv2
import numpy as np
from PIL import Image
import torch
from ml.models import ml
from logger import logger

from services.detector_ops.box_expander import expand_box_to_bubble
from services.detector_ops.overlap_resolver import resolve_overlapping_bubbles
from services.detector_ops.reading_order import sort_manga_reading_order


def _area(box: List[float]) -> float:
    """Площадь бокса в формате xyxy."""
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _iou(a: List[float], b: List[float]) -> float:
    """Intersection-over-Union для двух боксов xyxy."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def detect_and_filter_bubbles(
    image: Image.Image,
    model_name: str = "yolo_manga.pt",
    conf_threshold: float = 0.25,
    detect_sfx: bool = False
) -> List[Dict[str, Any]]:
    """Детекция объектов (YOLO). Если detect_sfx=False, то SFX (класс 3) полностью игнорируется."""
    yolo = ml.get_yolo(model_name)
    if yolo is None:
        raise RuntimeError(f"Модель YOLO ({model_name}) не загружена")

    model_classes = getattr(yolo, "names", {})
    logger.info(
        f"[YOLO Детектор] Запуск '{model_name}' с порогом conf={conf_threshold}, detect_sfx={detect_sfx}. "
        f"Классы: {model_classes}"
    )

    img_width, img_height = image.size

    with ml.lock, torch.inference_mode():
        results = yolo.predict(image, conf=conf_threshold, verbose=False)
        raw_items: List[Tuple[List[float], int, float]] = []
        for box in results[0].boxes:
            cls_id = int(box.cls[0].item()) if (box.cls is not None and len(box.cls) > 0) else 0

            # Если детект SFX отключен — полностью игнорируем класс 3
            if not detect_sfx and cls_id == 3:
                continue

            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0].item()) if (box.conf is not None and len(box.conf) > 0) else 0.0
            raw_items.append((xyxy, cls_id, conf))

    del results

    # 1. Дедупликация почти совпадающих боксов (IoU > 0.7): оставляем более уверенный.
    #    Раньше два одинаковых бокса классов 0/1 взаимно уничтожали друг друга.
    raw_items.sort(
        key=lambda item: (item[2], _area(item[0])),
        reverse=True,
    )
    deduped: List[Tuple[List[float], int, float]] = []
    for item in raw_items:
        if all(_iou(item[0], kept[0]) <= 0.7 for kept in deduped):
            deduped.append(item)
    duplicates_removed = len(raw_items) - len(deduped)

    # 2. Удаление вложенных рамок: внешний бокс убираем, только если он заметно больше
    #    и внутренний бокс целиком лежит в нём с допуском 15px.
    filtered_items: List[Tuple[List[float], int]] = []
    nested_removed = 0
    for i, (box_a, cls_a, _) in enumerate(deduped):
        x1_a, y1_a, x2_a, y2_a = box_a
        area_a = _area(box_a)
        is_outer = False

        for j, (box_b, _, _) in enumerate(deduped):
            if i == j:
                continue
            x1_b, y1_b, x2_b, y2_b = box_b

            if area_a <= _area(box_b) * 1.15:
                continue

            if (x1_a - 15 <= x1_b and y1_a - 15 <= y1_b and
                    x2_a + 15 >= x2_b and y2_a + 15 >= y2_b):
                is_outer = True
                break

        if is_outer:
            nested_removed += 1
        else:
            filtered_items.append((box_a, cls_a))

    logger.debug(
        f"[YOLO Детектор] Фильтрация: удалено дубликатов {duplicates_removed}, "
        f"вложенных рамок {nested_removed}"
    )

    np_img = np.array(image.convert("RGB"))
    gray_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)

    int_boxes: List[Tuple[int, int, int, int, int]] = []
    for box_coords, cls_id in filtered_items:
        x1, y1, x2, y2 = box_coords
        ix1 = int(max(0, x1))
        iy1 = int(max(0, y1))
        ix2 = int(min(img_width, x2))
        iy2 = int(min(img_height, y2))
        if ix2 > ix1 + 4 and iy2 > iy1 + 4:
            int_boxes.append((ix1, iy1, ix2, iy2, cls_id))

    boxes: List[Dict[str, Any]] = []

    # 1. Разводим перекрывающиеся сдвоенные бабблы до расширения
    int_boxes = resolve_overlapping_bubbles(gray_img, int_boxes)
    plain_coords = [(b[0], b[1], b[2], b[3]) for b in int_boxes]

    expanded_int_boxes: List[Tuple[int, int, int, int, int]] = []
    for idx, (ix1, iy1, ix2, iy2, cls_id) in enumerate(int_boxes):
        other_boxes = [b for j, b in enumerate(plain_coords) if j != idx]

        if cls_id in (0, 1):
            ex1, ey1, ex2, ey2 = expand_box_to_bubble(gray_img, ix1, iy1, ix2, iy2, other_boxes)
        else:
            ex1, ey1, ex2, ey2 = ix1, iy1, ix2, iy2

        expanded_int_boxes.append((ex1, ey1, ex2, ey2, cls_id))

    # 2. Повторно проверяем на случай касания после дотягивания до овала
    expanded_int_boxes = resolve_overlapping_bubbles(gray_img, expanded_int_boxes)

    for ex1, ey1, ex2, ey2, cls_id in expanded_int_boxes:
        px1 = max(0.0, ex1 / img_width)
        py1 = max(0.0, ey1 / img_height)
        px2 = min(1.0, ex2 / img_width)
        py2 = min(1.0, ey2 / img_height)

        boxes.append({
            "x": px1,
            "y": py1,
            "width": max(0.01, px2 - px1),
            "height": max(0.01, py2 - py1),
            "class_id": cls_id,
        })

    boxes = sort_manga_reading_order(boxes, gray_img=gray_img)

    counts = Counter(b["class_id"] for b in boxes)
    readable_counts = {model_classes.get(cid, f"Класс {cid}"): count for cid, count in counts.items()}
    logger.info(f"[YOLO Детектор] Найдено объектов: {len(boxes)}. Распределение: {readable_counts}")

    return boxes

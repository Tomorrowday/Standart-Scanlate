# services/cleaner_ops/bubble_cleaner.py
# Очистка отдельного речевого бабла (White / Smart Stroke LaMa / Box LaMa с учётом поворота)

from typing import Optional, Tuple
import cv2
import numpy as np

from services.cleaner_ops.image_io import get_box_geometry
from services.cleaner_ops.white_bubble import (
    is_mostly_white_bubble,
    clean_white_bubble_patch,
    _create_shape_mask,
)
from services.cleaner_ops.stroke_mask import build_text_stroke_mask
from services.cleaner_ops.brush_unet_mask import predict_text_brush_mask
from services.cleaner_ops.lama_inpaint import (
    LAMA_HARD_SAFE_DIM,
    inpaint_patch_with_lama,
    blend_inpainted_patch,
    _get_affine_points,
    _blend_rotated_patch,
)
from logger import logger

# Минимальная сторона контекстного кропа и верхняя граница, за которой LaMa
# принудительно даунскейлит патч и теряет чёткость скринтона
_MIN_CROP_SIDE = 512
_MAX_CROP_SIDE = LAMA_HARD_SAFE_DIM


def _resolve_context_pads(bw: int, bh: int, min_pad: int) -> Tuple[int, int]:
    """
    Считает паддинг контекста независимо по каждой оси.

    Раньше кроп раздувался до квадрата `max(bw, bh) * 2.2`: для узкого длинного
    столбца (130x850) это давало 1870px по X, принудительный даунскейл и потерю
    чёткости скринтона. Теперь по каждой оси достаточно `min_pad` живого фона,
    а минимальный размер кропа (512px) добирается только по короткой оси.
    """
    def axis_pad(size: int) -> int:
        pad = max(min_pad, (_MIN_CROP_SIDE - size + 1) // 2)
        if size + 2 * pad > _MAX_CROP_SIDE:
            pad = max(0, (_MAX_CROP_SIDE - size) // 2)
        return pad

    return axis_pad(bw), axis_pad(bh)


def _resolve_lama_roi_mask(
    image_np: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    force_mode: str,
    class_id: int = 0,
    brush_model: str = "",
    brush_threshold: float = 0.5,
    brush_extra_dilate: int = 0,
    brush_max_side: int = 512,
) -> Optional[np.ndarray]:
    """
    Возвращает маску для LaMa внутри ROI [y1:y2, x1:x2]:
    - при force_mode == 'lama_box' — сплошной прямоугольник;
    - для Free-Text (class_id == 2) или ручного режима LaMa — нейросетевая U-Net-маска из weights/brush;
    - иначе — капсульная маска текста OpenCV (полосы-капсулы по столбцам/строкам).

    Если ни U-Net, ни надёжные штрихи не дали достаточной площади, возвращает None:
    клин пропускается, чтобы прямоугольная маска не уничтожила фон.
    """
    h, w = y2 - y1, x2 - x1
    if force_mode == "lama_box":
        return _create_shape_mask(h, w, "rect")

    min_pixels = max(12, int(h * w * 0.004))

    use_unet = (
        (class_id == 2 or force_mode == "lama")
        and bool(brush_model)
        and brush_model != "opencv"
    )
    if use_unet:
        unet_mask = predict_text_brush_mask(
            image_np, x1, y1, x2, y2,
            model_name=brush_model,
            threshold=brush_threshold,
            extra_dilate=brush_extra_dilate,
            max_side=brush_max_side,
        )
        if np.count_nonzero(unet_mask) >= min_pixels:
            logger.debug(f"Маска клина: unet ({brush_model})")
            return unet_mask
        logger.debug("Маска клина: U-Net пустая/мала, откат на OpenCV")

    stroke_mask = build_text_stroke_mask(image_np, x1, y1, x2, y2)
    if np.count_nonzero(stroke_mask) >= min_pixels:
        logger.debug("Маска клина: opencv")
        return stroke_mask

    return None


def clean_speech_bubble(
    image_np: np.ndarray,
    box: dict,
    force_mode: str = "auto",
    clean_model_name: str = "",
    min_pad: int = 80,
    brush_model: str = "opencv",
    brush_threshold: float = 0.5,
    brush_extra_dilate: int = 0,
    brush_max_side: int = 512,
    downscale: bool = False,
) -> str:
    cx, cy, bw, bh, rot, _ = get_box_geometry(image_np, box)
    img_h, img_w = image_np.shape[:2]
    class_id = int(box.get("class_id", 0))

    if force_mode == "white":
        target_use_white = True
    elif force_mode in ("lama", "lama_box"):
        target_use_white = False
    elif class_id in (0, 1):
        target_use_white = True
    elif class_id == 2:
        target_use_white = False
    else:
        target_use_white = None

    if abs(rot) < 0.5:
        x1 = max(0, int(cx - bw / 2.0))
        y1 = max(0, int(cy - bh / 2.0))
        x2 = min(img_w, x1 + bw)
        y2 = min(img_h, y1 + bh)

        roi = image_np[y1:y2, x1:x2]
        if roi.size == 0:
            return "skipped"

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        use_white = target_use_white if target_use_white is not None else is_mostly_white_bubble(roi, gray)

        if use_white:
            clean_white_bubble_patch(roi, gray)
            image_np[y1:y2, x1:x2] = roi
            return "white"

        # Строим точечную маску штрихов текста + обводки вместо вырезания всей коробки
        box_mask = _resolve_lama_roi_mask(
            image_np, x1, y1, x2, y2, force_mode,
            class_id=class_id,
            brush_model=brush_model,
            brush_threshold=brush_threshold,
            brush_extra_dilate=brush_extra_dilate,
            brush_max_side=brush_max_side,
        )
        if box_mask is None:
            return "skipped"

        pad_x, pad_y = _resolve_context_pads(bw, bh, min_pad)

        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(img_w, x2 + pad_x)
        cy2 = min(img_h, y2 + pad_y)

        crop_bgr = image_np[cy1:cy2, cx1:cx2].copy()
        crop_mask = np.zeros(crop_bgr.shape[:2], dtype=np.uint8)
        crop_mask[y1 - cy1:y1 - cy1 + roi.shape[0], x1 - cx1:x1 - cx1 + roi.shape[1]] = box_mask

        inpainted = inpaint_patch_with_lama(
            crop_bgr, crop_mask,
            clean_model_name=clean_model_name,
            downscale=downscale,
        )
        blend_inpainted_patch(image_np, inpainted, crop_mask, cx1, cy1, cx2, cy2)
        return "inpaint"

    # Ветка для повёрнутых рамок (abs(rot) >= 0.5)
    src_pts, dst_pts = _get_affine_points(cx, cy, bw, bh, rot)
    m_extract = cv2.getAffineTransform(src_pts, dst_pts)
    upright_patch = cv2.warpAffine(
        image_np, m_extract, (bw, bh),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )

    gray_patch = cv2.cvtColor(upright_patch, cv2.COLOR_BGR2GRAY)
    use_white = target_use_white if target_use_white is not None else is_mostly_white_bubble(upright_patch, gray_patch)

    if use_white:
        clean_white_bubble_patch(upright_patch, gray_patch)
        cleaned_upright = upright_patch
        blend_mask = None
        used_method = "white"
    else:
        pad_x, pad_y = _resolve_context_pads(bw, bh, min_pad)
        pw = bw + 2 * pad_x
        ph = bh + 2 * pad_y

        dst_pts_padded = np.float32([[pad_x, pad_y], [pad_x + bw, pad_y], [pad_x, pad_y + bh]])
        m_extract_padded = cv2.getAffineTransform(src_pts, dst_pts_padded)
        padded_patch = cv2.warpAffine(
            image_np, m_extract_padded, (pw, ph),
            flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

        roi_mask = _resolve_lama_roi_mask(
            padded_patch, pad_x, pad_y, pad_x + bw, pad_y + bh, force_mode,
            class_id=class_id,
            brush_model=brush_model,
            brush_threshold=brush_threshold,
            brush_extra_dilate=brush_extra_dilate,
            brush_max_side=brush_max_side,
        )
        if roi_mask is None:
            return "skipped"
        clean_mask = np.zeros((ph, pw), dtype=np.uint8)
        clean_mask[pad_y:pad_y + bh, pad_x:pad_x + bw] = roi_mask

        inpainted_padded = inpaint_patch_with_lama(
            padded_patch, clean_mask,
            clean_model_name=clean_model_name,
            downscale=downscale,
        )
        # НЕ смешиваем внутри выпрямленного патча: иначе маска дважды размывается
        # (здесь и при обратном повороте) и остаётся полупрозрачный край старой буквы.
        # Единственное смешивание — в _blend_rotated_patch по дилатированной маске.
        cleaned_upright = inpainted_padded[pad_y:pad_y + bh, pad_x:pad_x + bw]
        blend_mask = roi_mask
        used_method = "inpaint"

    # Для LaMa возвращаем на страницу только заклиненные штрихи, чтобы фон вокруг них
    # не проходил повторную интерполяцию при обратном повороте патча.
    _blend_rotated_patch(
        image_np, cleaned_upright, src_pts, dst_pts, bw, bh, "rect", mask_patch=blend_mask
    )
    return used_method


def spot_clean_region(
    image_np: np.ndarray,
    box: dict,
    method: str = "auto",
    clean_model_name: str = "",
    brush_model: str = "opencv",
    brush_threshold: float = 0.5,
    brush_extra_dilate: int = 0,
    brush_max_side: int = 512,
    downscale: bool = False,
) -> str:
    min_pad = 90 if method in ("lama", "lama_box") else 80
    return clean_speech_bubble(
        image_np, box,
        force_mode=method,
        clean_model_name=clean_model_name,
        min_pad=min_pad,
        brush_model=brush_model,
        brush_threshold=brush_threshold,
        brush_extra_dilate=brush_extra_dilate,
        brush_max_side=brush_max_side,
        downscale=downscale,
    )

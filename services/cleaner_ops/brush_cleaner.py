# services/cleaner_ops/brush_cleaner.py
# Очистка произвольного мазка кисти пользователя с кластеризацией мазков (защита от переполнения VRAM)

import cv2
import numpy as np

from services.cleaner_ops.lama_inpaint import inpaint_patch_with_lama, blend_inpainted_patch


def inpaint_by_brush_mask(
    image_np: np.ndarray,
    mask_gray: np.ndarray,
    mode: str = "lama",
    clean_model_name: str = "",
    downscale: bool = False,
) -> np.ndarray:
    binary_mask = ((mask_gray > 127).astype(np.uint8)) * 255
    if mode == "white":
        image_np[binary_mask > 0] = [255, 255, 255]
        return image_np

    if mode == "black":
        image_np[binary_mask > 0] = [0, 0, 0]
        return image_np

    if np.count_nonzero(binary_mask) == 0:
        return image_np

    img_h, img_w = image_np.shape[:2]

    # Объединяем близкие штрихи кисти (в пределах ~96px друг от друга) в единые кластеры,
    # но НЕ сливаем случайные точки на разных концах страницы в один 4K-кроп
    cluster_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (95, 95))
    clustered = cv2.dilate(binary_mask, cluster_kernel, iterations=1)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(clustered, connectivity=8)

    for lbl in range(1, num_labels):
        x = int(stats[lbl, cv2.CC_STAT_LEFT])
        y = int(stats[lbl, cv2.CC_STAT_TOP])
        w = int(stats[lbl, cv2.CC_STAT_WIDTH])
        h = int(stats[lbl, cv2.CC_STAT_HEIGHT])

        cluster_roi_mask = np.where(labels[y:y + h, x:x + w] == lbl, binary_mask[y:y + h, x:x + w], 0)
        pts = cv2.findNonZero(cluster_roi_mask)
        if pts is None:
            continue

        bx, by, bw, bh = cv2.boundingRect(pts)
        rx, ry = x + bx, y + by

        target_size = max(512, int(max(bw, bh) * 2.0))
        pad_x = max(70, (target_size - bw) // 2)
        pad_y = max(70, (target_size - bh) // 2)

        x1 = max(0, rx - pad_x)
        y1 = max(0, ry - pad_y)
        x2 = min(img_w, rx + bw + pad_x)
        y2 = min(img_h, ry + bh + pad_y)

        crop_bgr = image_np[y1:y2, x1:x2].copy()
        crop_mask = np.zeros(crop_bgr.shape[:2], dtype=np.uint8)

        # Переносим только мазки текущего кластера
        sub_labels = labels[y1:y2, x1:x2]
        sub_binary = binary_mask[y1:y2, x1:x2]
        crop_mask[sub_labels == lbl] = sub_binary[sub_labels == lbl]

        inpainted_crop = inpaint_patch_with_lama(
            crop_bgr, crop_mask,
            clean_model_name=clean_model_name,
            downscale=downscale,
        )
        blend_inpainted_patch(image_np, inpainted_crop, crop_mask, x1, y1, x2, y2)

    return image_np

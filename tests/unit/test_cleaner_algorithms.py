# tests/unit/test_cleaner_algorithms.py
# Unicode-пути, белый клин, маска «виртуальной кисти» и препроцессинг U-Net.

import cv2
import math
import numpy as np
import pytest

from services.cleaner_ops.brush_unet_mask import (
    apply_morphology,
    compute_pad,
    make_box_prior,
    prepare_tensor,
    restore_mask,
)
from services.cleaner_ops.image_io import load_image_cv2, save_image_cv2
from services.cleaner_ops.stroke_mask import build_text_stroke_mask
from services.cleaner_ops.white_bubble import clean_white_bubble_patch, is_mostly_white_bubble

pytestmark = pytest.mark.unit


# --- image_io: Unicode-пути -------------------------------------------------------


def test_load_and_save_image_with_cyrillic_and_japanese_path(tmp_path):
    target = tmp_path / "манга" / "東京" / "ページ_01.png"
    image = np.full((24, 32, 3), 255, dtype=np.uint8)
    image[5:10, 5:10] = (0, 0, 0)

    assert save_image_cv2(str(target), image) is True
    assert target.exists()

    loaded = load_image_cv2(str(target))
    assert loaded.shape == (24, 32, 3)
    assert loaded.dtype == np.uint8
    assert int(loaded[7, 7, 0]) == 0


# --- white_bubble -----------------------------------------------------------------


def _white_bubble_roi() -> np.ndarray:
    """Белый бабл с лучистой (пунктирной) рамкой и текстом в центре."""
    roi = np.full((140, 220, 3), 255, dtype=np.uint8)
    cx, cy, rx, ry = 110, 70, 95, 60
    for deg in range(0, 360, 8):
        angle = math.radians(deg)
        c, s = math.cos(angle), math.sin(angle)
        p1 = (int(cx + rx * 0.90 * c), int(cy + ry * 0.90 * s))
        p2 = (int(cx + rx * c), int(cy + ry * s))
        cv2.line(roi, p1, p2, (0, 0, 0), 3, lineType=cv2.LINE_AA)
    cv2.rectangle(roi, (95, 60), (125, 80), (0, 0, 0), -1)
    return roi


def test_clean_white_bubble_removes_text_but_keeps_border():
    roi = _white_bubble_roi()
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    dark_before = int(np.count_nonzero(roi.min(axis=2) < 128))

    clean_white_bubble_patch(roi, gray)

    # Текст в центре закрашен белым.
    assert int(roi[70, 110].min()) >= 250
    # Лучистая рамка не уничтожена.
    dark_after = int(np.count_nonzero(roi.min(axis=2) < 128))
    assert 0 < dark_after < dark_before


def test_is_mostly_white_bubble():
    roi = _white_bubble_roi()
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    assert is_mostly_white_bubble(roi, gray) is True

    dark = np.full((120, 200, 3), 120, dtype=np.uint8)
    dark_gray = cv2.cvtColor(dark, cv2.COLOR_BGR2GRAY)
    assert is_mostly_white_bubble(dark, dark_gray) is False

    empty = np.zeros((0, 0), dtype=np.uint8)
    assert is_mostly_white_bubble(empty, empty) is False


# --- stroke_mask: две колонки и живой коридор -------------------------------------


def _two_columns_page() -> tuple[np.ndarray, tuple[int, int, int, int]]:
    img = np.full((200, 260, 3), 255, dtype=np.uint8)
    for y in (30, 62, 94, 126, 158):
        cv2.rectangle(img, (35, y), (55, y + 18), (0, 0, 0), -1)
        cv2.rectangle(img, (100, y), (120, y + 18), (0, 0, 0), -1)
    return img, (25, 20, 130, 180)


def test_stroke_mask_keeps_white_gutter_between_columns():
    img, (x1, y1, x2, y2) = _two_columns_page()

    mask = build_text_stroke_mask(img, x1, y1, x2, y2)

    assert mask.shape == (y2 - y1, x2 - x1)
    assert np.count_nonzero(mask) > 0
    # Штрихи обеих колонок попали в маску.
    left_rel = 40 - x1
    right_rel = 110 - x1
    assert np.count_nonzero(mask[:, left_rel - 3:left_rel + 3]) > 0
    assert np.count_nonzero(mask[:, right_rel - 3:right_rel + 3]) > 0
    # Середина коридора (>= 10 px живого фона) не затирается.
    gutter = mask[:, 50:60]
    assert np.count_nonzero(gutter) == 0


def test_stroke_mask_empty_frame_returns_empty_mask():
    img = np.full((120, 120, 3), 255, dtype=np.uint8)

    mask = build_text_stroke_mask(img, 20, 20, 100, 100)

    assert mask.shape == (80, 80)
    assert np.count_nonzero(mask) == 0


# --- brush_unet_mask: контракт без загрузки модели --------------------------------


def test_compute_pad_and_box_prior():
    assert compute_pad(100, 100) == 24
    assert compute_pad(400, 100) == 60

    prior = make_box_prior((50, 60), (10, 5, 40, 30))
    assert prior.shape == (50, 60)
    assert prior[5, 10] == 1.0
    assert prior[29, 39] == 1.0
    assert prior[0, 0] == 0.0
    assert prior[49, 59] == 0.0

    clamped = make_box_prior((10, 10), (-5, -5, 999, 999))
    assert clamped.min() == 1.0


def test_prepare_tensor_contract_no_upscale_and_multiple_of_32():
    crop = np.full((50, 100, 3), 128, dtype=np.uint8)
    prior = make_box_prior((50, 100), (10, 10, 40, 30))

    tensor, meta = prepare_tensor(crop, prior, max_side=512)

    assert tuple(tensor.shape)[0] == 1
    assert tuple(tensor.shape)[1] == 4
    assert tensor.shape[2] % 32 == 0
    assert tensor.shape[3] % 32 == 0
    # Без апскейла: маленький кроп только паддится.
    assert tensor.shape[2] >= 50 and tensor.shape[3] >= 100
    assert float(tensor.min()) >= 0.0
    assert float(tensor.max()) <= 1.0
    assert meta["scale"] == 1.0
    assert meta["crop_w"] == 100 and meta["crop_h"] == 50

    # Канал prior отдельно: 1 внутри рамки, 0 в reflect-паддинге.
    prior_channel = tensor[0, 3].numpy()
    assert float(prior_channel.max()) == 1.0
    assert float(prior_channel.min()) == 0.0


def test_prepare_tensor_downscales_only_when_larger_than_max_side():
    crop = np.full((640, 320, 3), 200, dtype=np.uint8)
    prior = make_box_prior((640, 320), (0, 0, 320, 640))

    tensor, meta = prepare_tensor(crop, prior, max_side=256)

    assert meta["scale"] == pytest.approx(0.4)
    assert tensor.shape[2] % 32 == 0 and tensor.shape[3] % 32 == 0
    assert tensor.shape[2] <= 256 + 31 and tensor.shape[3] <= 256 + 31


def test_restore_mask_returns_original_crop_size():
    crop = np.full((50, 100, 3), 255, dtype=np.uint8)
    prior = make_box_prior((50, 100), (20, 10, 80, 40))
    tensor, meta = prepare_tensor(crop, prior, max_side=512)

    pred = tensor[:, 3:4]  # (1,1,H,W), значения 0/1
    mask = restore_mask(pred, meta, threshold=0.5)

    assert mask.shape == (50, 100)
    assert set(np.unique(mask)).issubset({0, 255})
    assert np.count_nonzero(mask) > 0


def test_apply_morphology_dilates_erodes_and_keeps_zero():
    mask = np.zeros((21, 21), dtype=np.uint8)
    mask[10, 10] = 255

    assert np.count_nonzero(apply_morphology(mask, 2)) > 1
    assert apply_morphology(mask, 0) is mask

    dilated = apply_morphology(mask, 2)
    eroded = apply_morphology(dilated, -2)
    assert eroded.shape == mask.shape
    assert eroded[10, 10] == 255

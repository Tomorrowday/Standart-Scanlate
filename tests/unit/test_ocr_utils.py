# tests/unit/test_ocr_utils.py
# Нормализация японского OCR-текста и затирание соседних баблов.

import cv2
import numpy as np
import pytest
from PIL import Image

from services.ocr_ops.crop_edge_cleaner import _clean_ocr_crop_from_foreign_text
from services.ocr_ops.neighbor_masking import _mask_foreign_neighbor_regions_in_page_coords
from services.ocr_ops.text_normalizer import normalize_ocr_japanese_text

pytestmark = pytest.mark.unit


def test_normalize_nfkc_and_remove_spaces_between_cjk():
    assert normalize_ocr_japanese_text("ＡＢＣ１２３") == "ABC123"
    assert normalize_ocr_japanese_text("東京 タワー") == "東京タワー"
    assert normalize_ocr_japanese_text("待 って") == "待って"


def test_normalize_collapses_ellipsis_and_colons():
    assert normalize_ocr_japanese_text("待って...") == "待って…"
    assert normalize_ocr_japanese_text("本当：：すごい") == "本当…すごい"
    assert normalize_ocr_japanese_text("そう：ね") == "そう…ね"
    assert normalize_ocr_japanese_text("え … と") == "え…と"
    assert normalize_ocr_japanese_text("1:30") == "1:30"  # время не трогаем


def test_normalize_handles_empty_and_line_breaks():
    assert normalize_ocr_japanese_text("") == ""
    assert normalize_ocr_japanese_text("一行\n二行\t三行") == "一行二行三行"


def test_mask_foreign_neighbor_regions_erases_neighbor_but_keeps_target_core():
    arr = np.full((200, 200, 3), 255, dtype=np.uint8)
    # Текст целевого бабла A.
    arr[30:70, 30:70] = (0, 0, 0)
    # Текст соседа B внутри зоны пересечения.
    arr[90:110, 80:110] = (0, 0, 0)

    target_box = (20, 20, 120, 120)
    neighbor = {"x": 70 / 200, "y": 80 / 200, "width": 110 / 200, "height": 100 / 200, "class_id": 0}

    _mask_foreign_neighbor_regions_in_page_coords(
        arr,
        (0, 0, 200, 200),
        target_box,
        (200, 200),
        other_boxes=[neighbor],
    )

    # Соседний текст в спорной зоне затёрт белым.
    assert int(arr[100, 95].min()) == 255
    # Собственное ядро целевого бабла сохранено.
    assert int(arr[50, 50].max()) == 0


def test_mask_foreign_ignores_non_bubble_neighbors():
    arr = np.full((200, 200, 3), 255, dtype=np.uint8)
    arr[90:110, 80:110] = (0, 0, 0)

    neighbor = {"x": 0.35, "y": 0.4, "width": 0.55, "height": 0.5, "class_id": 3}
    _mask_foreign_neighbor_regions_in_page_coords(
        arr, (0, 0, 200, 200), (20, 20, 120, 120), (200, 200), other_boxes=[neighbor]
    )

    assert int(arr[100, 95].max()) == 0


def test_clean_ocr_crop_erases_edge_wall_and_keeps_center_text():
    img = Image.new("RGB", (150, 150), "white")
    arr = np.array(img)
    arr[20:130, 0:6] = (0, 0, 0)      # стенка бабла, прилипшая к краю
    arr[60:90, 60:90] = (0, 0, 0)     # собственный текст в центре
    img = Image.fromarray(arr)

    cleaned = _clean_ocr_crop_from_foreign_text(
        img, (0, 0, 150, 150), (150, 150), class_id=0, other_boxes=None
    )
    out = np.array(cleaned)

    assert int(out[75, 75].max()) == 0
    assert int(out[75, 2].min()) == 255


def test_clean_ocr_crop_skips_dark_or_sfx_regions():
    dark = Image.new("RGB", (60, 60), (60, 60, 60))
    assert _clean_ocr_crop_from_foreign_text(
        dark, (0, 0, 60, 60), (60, 60), class_id=0
    ) is dark

    white = Image.new("RGB", (60, 60), "white")
    arr = np.array(white)
    arr[0:5, 0:60] = (0, 0, 0)
    sfx_img = Image.fromarray(arr)
    out = np.array(
        _clean_ocr_crop_from_foreign_text(sfx_img, (0, 0, 60, 60), (60, 60), class_id=2)
    )
    assert int(out[2, 30].max()) == 0  # класс 2 (SFX) не чистится

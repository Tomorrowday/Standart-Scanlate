# tests/heavy/test_ml_yolo.py
# Тяжёлый тест: реальный инференс YOLO на синтетической странице.

import pytest
from PIL import Image, ImageDraw

import config
from services.detector_ops.yolo_detector import detect_and_filter_bubbles

pytestmark = pytest.mark.heavy


def _available_detector() -> str:
    detectors = config.get_available_detectors()
    for name in detectors:
        if (config.DETECT_MODELS_DIR / name).exists() or (config.WEIGHTS_DIR / name).exists():
            return name
    pytest.skip("В weights/detect-bubble нет ни одной .pt-модели YOLO")


def _synthetic_page() -> Image.Image:
    image = Image.new("RGB", (640, 640), "white")
    draw = ImageDraw.Draw(image)
    # Два белых бабла с чёрной обводкой и «текстом».
    for cx, cy in ((180, 180), (460, 420)):
        draw.ellipse((cx - 100, cy - 80, cx + 100, cy + 80), outline="black", width=4)
        for line in range(-2, 3):
            y = cy + line * 18
            draw.line((cx - 45, y, cx + 45, y), fill="black", width=4)
    # Крупный SFX-подобный штрих.
    draw.line((260, 520, 380, 600), fill="black", width=10)
    draw.line((380, 520, 260, 600), fill="black", width=10)
    return image


def test_yolo_detects_and_filters_sfx():
    from ml.models import release_vram

    model_name = _available_detector()
    image = _synthetic_page()

    try:
        without_sfx = detect_and_filter_bubbles(image, model_name=model_name, detect_sfx=False)
        assert isinstance(without_sfx, list)
        assert all(b["class_id"] != 3 for b in without_sfx)
        assert [b["order_index"] for b in without_sfx] == list(range(1, len(without_sfx) + 1))
        for b in without_sfx:
            assert 0.0 <= b["x"] <= 1.0
            assert 0.0 <= b["y"] <= 1.0
            assert b["width"] > 0 and b["height"] > 0

        with_sfx = detect_and_filter_bubbles(image, model_name=model_name, detect_sfx=True)
        assert isinstance(with_sfx, list)
        assert len(with_sfx) >= len(without_sfx)
    finally:
        release_vram()

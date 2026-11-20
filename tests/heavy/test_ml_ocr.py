# tests/heavy/test_ml_ocr.py
# Тяжёлый тест: реальный прогон дефолтного OCR-пайплайна.

import pytest
from PIL import Image, ImageDraw

from services.ocr import ocr_image_region

pytestmark = pytest.mark.heavy


def test_default_ocr_pipeline_runs_on_synthetic_image():
    from ml.models import ml, release_vram

    image = Image.new("RGB", (320, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 60, 280, 140), outline="black", width=3)
    for y in (80, 100, 120):
        draw.line((70, y, 250, y), fill="black", width=5)

    try:
        try:
            ml.get_ocr("manga-ocr-base")
        except Exception as exc:  # нет весов/сети/зависимостей — тяжёлый тест пропускается
            pytest.skip(f"Дефолтная OCR-модель недоступна: {exc}")

        text = ocr_image_region(
            image,
            x=0.1,
            y=0.2,
            width=0.8,
            height=0.6,
            rotation=0.0,
            class_id=0,
            ocr_model_name="manga-ocr-base",
        )
        assert isinstance(text, str)
    finally:
        release_vram()

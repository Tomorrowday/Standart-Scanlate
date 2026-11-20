# tests/heavy/test_ml_lama_and_brush.py
# Тяжёлые тесты: реальный LaMa, клин бабла и U-Net-маска текста (weights/brush).

import cv2
import numpy as np
import pytest
import torch

import config
from services.cleaner_ops.brush_cleaner import inpaint_by_brush_mask
from services.cleaner_ops.brush_unet_mask import predict_text_brush_mask
from services.cleaner_ops.bubble_cleaner import clean_speech_bubble
from services.cleaner_ops.lama_inpaint import inpaint_patch_with_lama

pytestmark = pytest.mark.heavy


def _lama_model_name() -> str:
    candidates = sorted(config.CLEAN_MODELS_DIR.glob("*.pt"))
    if not candidates:
        candidates = sorted(config.WEIGHTS_DIR.glob("*lama*.pt"))
    if not candidates:
        pytest.skip("В weights/clean-lama нет .pt-модели LaMa")
    return candidates[0].name


def _brush_model_name() -> str:
    candidates = sorted(config.BRUSH_MODELS_DIR.glob("*.pt"))
    if not candidates:
        pytest.skip("В weights/brush нет TorchScript-модели U-Net")
    return candidates[0].name


def _text_patch(size: int = 160) -> tuple[np.ndarray, np.ndarray]:
    patch = np.full((size, size, 3), 255, dtype=np.uint8)
    cv2.rectangle(patch, (30, 40), (size - 30, 55), (0, 0, 0), -1)
    cv2.rectangle(patch, (30, 70), (size - 50, 85), (0, 0, 0), -1)
    cv2.rectangle(patch, (30, 100), (size - 40, 115), (0, 0, 0), -1)
    mask = np.zeros((size, size), dtype=np.uint8)
    mask[40:115, 30 : size - 30] = 255
    return patch, mask


def test_lama_inpaint_returns_same_shape_for_both_downscale_modes():
    from ml.models import release_vram

    model_name = _lama_model_name()
    patch, mask = _text_patch()

    try:
        for downscale in (False, True):
            result = inpaint_patch_with_lama(
                patch.copy(), mask.copy(), clean_model_name=model_name, downscale=downscale
            )
            assert result.shape == patch.shape
            assert result.dtype == np.uint8
    finally:
        release_vram()


def test_clean_speech_bubble_white_and_lama_paths():
    from ml.models import release_vram

    model_name = _lama_model_name()
    image = np.full((320, 320, 3), 255, dtype=np.uint8)
    cv2.ellipse(image, (160, 160), (110, 90), 0, 0, 360, (0, 0, 0), 3)
    for y in range(130, 200, 18):
        cv2.line(image, (110, y), (210, y), (0, 0, 0), 4)
    box = {"x": 0.18, "y": 0.22, "width": 0.64, "height": 0.56, "class_id": 0, "rotation": 0.0}

    try:
        white_img = image.copy()
        method = clean_speech_bubble(white_img, box, force_mode="auto", clean_model_name=model_name)
        assert method == "white"

        lama_img = image.copy()
        method = clean_speech_bubble(
            lama_img, box, force_mode="lama", clean_model_name=model_name, downscale=False
        )
        assert method in ("inpaint", "skipped")
        assert lama_img.shape == image.shape
    finally:
        release_vram()


def test_inpaint_by_brush_mask_clusters_strokes():
    from ml.models import release_vram

    model_name = _lama_model_name()
    image = np.full((360, 360, 3), 255, dtype=np.uint8)
    mask = np.zeros((360, 360), dtype=np.uint8)
    cv2.circle(mask, (60, 60), 18, 255, -1)
    cv2.circle(mask, (300, 300), 18, 255, -1)

    try:
        for downscale in (True, False):
            result = inpaint_by_brush_mask(
                image.copy(), mask, mode="lama",
                clean_model_name=model_name, downscale=downscale,
            )
            assert result.shape == image.shape
    finally:
        release_vram()


def test_brush_unet_contract_and_predict_text_mask():
    from ml.models import ml, release_vram

    model_name = _brush_model_name()

    try:
        wrapper = ml.load_brush(model_name)
        probe = torch.zeros(1, 4, 64, 64, dtype=torch.float32)
        with torch.inference_mode():
            out = wrapper.predict(probe)
        assert tuple(out.shape) == (1, 1, 64, 64)
        assert float(out.min()) >= 0.0
        assert float(out.max()) <= 1.0

        page = np.full((300, 300, 3), 255, dtype=np.uint8)
        for y in (80, 110, 140):
            cv2.line(page, (80, y), (220, y), (0, 0, 0), 6)

        mask = predict_text_brush_mask(
            page, 60, 60, 240, 180, model_name=model_name, threshold=0.5
        )
        assert mask.shape == (120, 180)
        assert mask.dtype == np.uint8
        assert set(np.unique(mask)).issubset({0, 255})
    finally:
        release_vram()

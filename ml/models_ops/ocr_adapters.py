# ml/models_ops/ocr_adapters.py
# Адаптеры Hayai OCR / PaddleOCR-VL и фабрика выбора OCR-движка по весам в weights/ocr/

import json
import logging

import torch
from PIL import Image

import config
from ml.models_ops.transformers_compat import (
    _patch_tokenizer_config_if_needed,
    _patch_transformers_rope_compat,
)

logger = logging.getLogger("manga_translator.ml")


class HayaiOcrAdapter:
    """Адаптер Hayai OCR (v2.1 / v2.5 Nova / v2.7 Supernova) с нативным model.ocr()."""

    def __init__(self, model_dir, device: torch.device):
        from transformers import AutoModel, AutoProcessor

        self.device = device
        _patch_tokenizer_config_if_needed(model_dir)
        logger.info(f"Hayai OCR: загрузка процессора и модели из {model_dir}...")
        self.processor = AutoProcessor.from_pretrained(str(model_dir), trust_remote_code=True)
        self.model = AutoModel.from_pretrained(str(model_dir), trust_remote_code=True)
        self.model = self.model.to(device).eval()

    @torch.inference_mode()
    def __call__(self, image: Image.Image) -> str:
        img_rgb = image.convert("RGB")
        text = self.model.ocr(
            img_rgb,
            self.processor,
            max_patches=256,
            max_new_tokens=128,
            use_cuda_graph=False,
        )
        return str(text).strip() if text else ""


class PaddleOcrVlAdapter:
    """Адаптер PaddleOCR-VL (jzhang533/PaddleOCR-VL-For-Manga)."""

    def __init__(self, model_dir, device: torch.device):
        from transformers import AutoProcessor, AutoModelForCausalLM

        self.device = device
        _patch_tokenizer_config_if_needed(model_dir)
        _patch_transformers_rope_compat()
        dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
        logger.info(f"PaddleOCR-VL: загрузка процессора и модели из {model_dir}...")
        try:
            # Токенизатор PaddleOCR-VL основан на SentencePiece — нужен use_fast=False
            self.processor = AutoProcessor.from_pretrained(
                str(model_dir), trust_remote_code=True, use_fast=False
            )
        except Exception as e:
            logger.warning(f"PaddleOCR-VL: не удалось загрузить процессор с use_fast=False ({e}), пробуем по умолчанию...")
            self.processor = AutoProcessor.from_pretrained(str(model_dir), trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            trust_remote_code=True,
            torch_dtype=dtype,
        ).to(device).eval()

    @torch.inference_mode()
    def __call__(self, image: Image.Image) -> str:
        img_rgb = image.convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": img_rgb},
                    {"type": "text", "text": "OCR:"},
                ],
            }
        ]
        prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.processor(
            text=[prompt],
            images=[img_rgb],
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        generated_ids = self.model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            repetition_penalty=1.0,
        )
        input_len = inputs["input_ids"].shape[1]
        trimmed_ids = generated_ids[:, input_len:]
        out_text = self.processor.batch_decode(
            trimmed_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        return out_text.strip()


def _create_ocr_engine(model_name: str, device: torch.device):
    """Создаёт OCR-движок нужной архитектуры по имени папки в weights/ocr/."""
    name = (model_name or "manga-ocr-base").strip()
    model_dir = config.OCR_MODELS_DIR / name

    # Если папки нет в weights/ocr/ — загружаем стандартный MangaOcr
    if not model_dir.exists() or not (model_dir / "config.json").exists():
        logger.info(f"Загрузка стандартного MangaOCR (модель: {name})...")
        from manga_ocr import MangaOcr
        return MangaOcr()

    cfg_path = model_dir / "config.json"
    _patch_tokenizer_config_if_needed(model_dir)
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg_data = json.load(f)

    model_type = str(cfg_data.get("model_type", "")).lower()
    architectures = [str(a) for a in cfg_data.get("architectures", [])]

    # 1. Hayai OCR (v2.1 / v2.5 Nova / v2.7 Supernova)
    if model_type == "hayai" or "HayaiModel" in architectures or (model_dir / "modeling_hayai.py").exists():
        logger.info(f"Загрузка Hayai OCR из {model_dir} на {device}...")
        return HayaiOcrAdapter(model_dir, device)

    # 2. PaddleOCR-VL-For-Manga
    if model_type == "paddleocr_vl" or "PaddleOCRVLForConditionalGeneration" in architectures:
        logger.info(f"Загрузка PaddleOCR-VL из {model_dir} на {device}...")
        return PaddleOcrVlAdapter(model_dir, device)

    # 3. VisionEncoderDecoder (manga-ocr-base, muscgab/manga-ocr-base-CPT v2)
    logger.info(f"Загрузка MangaOCR-совместимой модели из {model_dir}...")
    from manga_ocr import MangaOcr
    return MangaOcr(pretrained_model_name_or_path=str(model_dir))


__all__ = ["HayaiOcrAdapter", "PaddleOcrVlAdapter", "_create_ocr_engine"]

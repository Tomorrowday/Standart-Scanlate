# ml/models_impl.py
# Загрузка MangaOCR, YOLO и LaMa с потокобезопасной блокировкой и управлением VRAM

import gc
import json
import logging
import threading
from typing import Optional, Dict, Any

import torch
import torch.nn.functional as F
import numpy as np
from PIL import Image

import config

logger = logging.getLogger("manga_translator.ml")


def _get_device() -> torch.device:
    """Определяет доступное устройство (CUDA или CPU)."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def release_vram() -> dict:
    """Принудительно очищает кэш видеопамяти PyTorch и сборщик мусора."""
    vram_before = 0.0
    vram_after = 0.0

    if torch.cuda.is_available():
        vram_before = torch.cuda.memory_allocated() / (1024 * 1024)

    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        vram_after = torch.cuda.memory_allocated() / (1024 * 1024)

    freed = max(0.0, vram_before - vram_after)
    return {
        "vram_before_mb": round(vram_before, 1),
        "vram_after_mb": round(vram_after, 1),
        "freed_mb": round(freed, 1),
    }


class AccurateLamaWrapper:
    """
    Обёртка над TorchScript-моделью LaMa.
    Использует дополнение (padding) без ресайза до кратности 8, что исключает замыливание арта манги.
    Потокобезопасна при параллельных запросах.
    """

    def __init__(self, model: torch.jit.ScriptModule, device: torch.device, lock: threading.Lock):
        self.model = model
        self.device = device
        self._lock = lock

    @torch.inference_mode()
    def __call__(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        orig_w, orig_h = image.size
        pad_w = (8 - orig_w % 8) % 8
        pad_h = (8 - orig_h % 8) % 8

        img_np = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        mask_np = np.array(mask.convert("L")).astype(np.float32)
        mask_np = (mask_np > 127).astype(np.float32)

        with self._lock:
            img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).to(self.device)
            mask_tensor = torch.from_numpy(mask_np).unsqueeze(0).unsqueeze(0).to(self.device)

            if pad_w > 0 or pad_h > 0:
                pad_mode = "reflect" if (pad_w < orig_w and pad_h < orig_h) else "replicate"
                img_tensor = F.pad(img_tensor, (0, pad_w, 0, pad_h), mode=pad_mode)
                mask_tensor = F.pad(mask_tensor, (0, pad_w, 0, pad_h), mode=pad_mode)

            try:
                out_tensor = self.model(img_tensor, mask_tensor)
                out_tensor = out_tensor[:, :, :orig_h, :orig_w]
                out_np = torch.clamp(out_tensor[0], 0, 1).permute(1, 2, 0).detach().cpu().float().numpy()
                out_uint8 = (out_np * 255.0).round().astype(np.uint8)
            finally:
                del img_tensor, mask_tensor
                if "out_tensor" in locals():
                    del out_tensor

        return Image.fromarray(out_uint8)


def _patch_tokenizer_config_if_needed(model_dir) -> None:
    """
    Чинит несовместимость моделей, сохранённых в transformers 5.0+
    (где PreTrainedTokenizerFast записан как TokenizersBackend), с transformers 4.x.
    """
    from pathlib import Path

    model_dir = Path(model_dir)
    tok_cfg_path = model_dir / "tokenizer_config.json"
    if not tok_cfg_path.exists():
        return

    try:
        import transformers

        # В transformers 4.x класса TokenizersBackend нет (он появился в 5.x),
        # поэтому регистрируем алиас и правим tokenizer_config.json.
        # В transformers 5.x ничего делать не нужно — класс уже существует.
        if hasattr(transformers, "TokenizersBackend"):
            return

        from transformers import PreTrainedTokenizerFast

        try:
            from transformers.models.auto import tokenization_auto

            if not hasattr(tokenization_auto, "TokenizersBackend"):
                tokenization_auto.TokenizersBackend = PreTrainedTokenizerFast
        except Exception:
            pass
        setattr(transformers, "TokenizersBackend", PreTrainedTokenizerFast)

        with open(tok_cfg_path, "r", encoding="utf-8") as f:
            tok_cfg = json.load(f)

        if tok_cfg.get("tokenizer_class") == "TokenizersBackend":
            tok_cfg["tokenizer_class"] = "PreTrainedTokenizerFast"
            with open(tok_cfg_path, "w", encoding="utf-8") as f:
                json.dump(tok_cfg, f, ensure_ascii=False, indent=2)
            logger.info(
                f"Авто-фикс {tok_cfg_path.name}: TokenizersBackend -> PreTrainedTokenizerFast"
            )
    except Exception as e:
        logger.warning(f"Не удалось проверить/обновить {tok_cfg_path}: {e}")


def _patch_transformers_rope_compat() -> None:
    """
    В transformers 5.x из ROPE_INIT_FUNCTIONS убрали тип "default",
    который всё ещё используют некоторые модели с trust_remote_code
    (например, PaddleOCR-VL-For-Manga). Возвращаем стандартный RoPE.
    """
    try:
        from transformers.modeling_rope_utils import ROPE_INIT_FUNCTIONS

        if "default" in ROPE_INIT_FUNCTIONS:
            return

        def _compute_default_rope_parameters(config, device=None, seq_len=None, **kwargs):
            base = float(getattr(config, "rope_theta", 10000.0))
            partial_rotary_factor = float(getattr(config, "partial_rotary_factor", 1.0))
            head_dim = getattr(config, "head_dim", None)
            if not head_dim:
                head_dim = config.hidden_size // config.num_attention_heads
            dim = int(head_dim * partial_rotary_factor)
            inv_freq = 1.0 / (
                base
                ** (
                    torch.arange(0, dim, 2, dtype=torch.int64, device=device).float()
                    / dim
                )
            )
            return inv_freq, 1.0

        ROPE_INIT_FUNCTIONS["default"] = _compute_default_rope_parameters
        logger.info("Авто-фикс RoPE: добавлен тип 'default' в ROPE_INIT_FUNCTIONS")
    except Exception as e:
        logger.warning(f"Не удалось применить фикс RoPE 'default': {e}")


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


class MLManager:
    """Менеджер ML-моделей: MangaOCR, YOLO, LaMa."""

    def __init__(self):
        self._device = _get_device()
        self._lock = threading.Lock()
        self._ocr_models: Dict[str, Any] = {}
        self._yolo_models: Dict[str, Any] = {}
        self._cleaners: Dict[str, Any] = {}
        self.gemini_model = None
        self.lama_downscale: bool = False
        logger.info(f"MLManager инициализирован. Устройство: {self._device}")

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    @property
    def device(self) -> torch.device:
        return self._device

    @property
    def mocr(self):
        """Обратная совместимость: возвращает дефолтную модель OCR."""
        return self.get_ocr("manga-ocr-base")

    def get_ocr(self, model_name: Optional[str] = None):
        """Возвращает инстанс OCR-движка по имени папки в weights/ocr или 'manga-ocr-base'."""
        name = (model_name or "manga-ocr-base").strip()
        with self._lock:
            if name in self._ocr_models:
                return self._ocr_models[name]

            # Чтобы не копить в VRAM сразу несколько тяжёлых OCR-моделей при переключении в настройках,
            # очищаем предыдущие загруженные OCR-модели перед загрузкой новой
            if self._ocr_models:
                self._ocr_models.clear()
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            engine = _create_ocr_engine(name, self._device)
            self._ocr_models[name] = engine
            return engine

    def load_manga_ocr(self, model_name: str = "manga-ocr-base"):
        return self.get_ocr(model_name)

    def get_yolo(self, model_name: Optional[str] = None):
        """Возвращает YOLO модель по имени файла или пути."""
        name = model_name or "yolo_manga.pt"
        with self._lock:
            if name in self._yolo_models:
                return self._yolo_models[name]

            candidates = [
                config.DETECT_MODELS_DIR / name,
                config.WEIGHTS_DIR / name,
                config.BASE_DIR / name,
            ]
            target_path = None
            for p in candidates:
                if p.exists():
                    target_path = str(p)
                    break

            if not target_path:
                target_path = str(config.YOLO_WEIGHTS_PATH)

            logger.info(f"Загрузка YOLO: {target_path}")
            from ultralytics import YOLO
            yolo_instance = YOLO(target_path)
            self._yolo_models[name] = yolo_instance
            return yolo_instance

    def load_cleaner(self, name: str = "anime-manga-big-lama.pt"):
        """Загружает модель LaMa."""
        if not name or name == "simple_lama":
            name = "anime-manga-big-lama.pt"

        with self._lock:
            if name in self._cleaners:
                return self._cleaners[name]

            candidates = [
                config.CLEAN_MODELS_DIR / name,
                config.WEIGHTS_DIR / name,
                config.BASE_DIR / name,
            ]
            target_path = None
            for p in candidates:
                if p.exists():
                    target_path = str(p)
                    break

            if not target_path:
                all_pt = list(config.CLEAN_MODELS_DIR.glob("*.pt")) or list(config.WEIGHTS_DIR.glob("*lama*.pt"))
                if all_pt:
                    target_path = str(all_pt[0])
                else:
                    raise FileNotFoundError(f"Файл модели клинера '{name}' не найден в папке weights/")

            logger.info(f"Загрузка TorchScript LaMa: {target_path}")
            base_model = torch.jit.load(target_path, map_location=self._device)
            base_model.eval()
            wrapper = AccurateLamaWrapper(base_model, self._device, self._lock)
            self._cleaners[name] = wrapper
            return wrapper

    def release_vram(self):
        return release_vram()

    def unload_all(self):
        with self._lock:
            self._ocr_models.clear()
            self._yolo_models.clear()
            self._cleaners.clear()
        release_vram()


# Экземпляры синглтона
ml = MLManager()
ml_manager = ml


def load_ml_models(preload: bool = False) -> MLManager:
    logger.info(f"Инициализация моделей (устройство: {ml.device})...")
    if preload:
        try:
            ml.load_manga_ocr()
        except Exception as e:
            logger.warning(f"Предзагрузка MangaOCR пропущена: {e}")
        try:
            ml.get_yolo()
        except Exception as e:
            logger.warning(f"Предзагрузка YOLO пропущена: {e}")
    return ml
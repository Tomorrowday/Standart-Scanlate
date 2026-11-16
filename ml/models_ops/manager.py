# ml/models_ops/manager.py
# Менеджер ML-моделей (MangaOCR, YOLO, LaMa), его синглтоны и точка предзагрузки

import gc
import logging
import threading
from typing import Optional, Dict, Any

import torch

import config
from ml.models_ops.lama_wrapper import AccurateLamaWrapper
from ml.models_ops.ocr_adapters import _create_ocr_engine
from ml.models_ops.vram import _get_device, release_vram

logger = logging.getLogger("manga_translator.ml")


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


__all__ = ["MLManager", "ml", "ml_manager", "load_ml_models"]

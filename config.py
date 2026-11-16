# config.py
"""
Конфигурация приложения и системных путей: загрузка .env, каталоги данных и весов, списки моделей.
Зависимости: os, re, warnings, logging, pathlib, dotenv
"""

import os
import re
import warnings
import logging
from pathlib import Path
from typing import Dict, List
from dotenv import load_dotenv

# 1. Подавляем шумные предупреждения и логи сторонних библиотек
warnings.filterwarnings("ignore")
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TQDM_DISABLE"] = "1"
os.environ["YOLO_VERBOSE"] = "False"
os.environ["ULTRALYTICS_AUTOINSTALL"] = "False"
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("ultralytics").setLevel(logging.ERROR)

# Настройка аллокатора PyTorch CUDA
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")

# Отключаем torch.compile для Hayai OCR (нестабилен на Windows)
os.environ.setdefault("HAYAI_DISABLE_COMPILE", "1")

# Загружаем переменные из .env
load_dotenv()

# Базовые пути проекта
BASE_DIR = Path(__file__).resolve().parent

# 1. Папка для файлов базы данных SQLite и словарей
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "manga_db.sqlite"

# 1.1. Отдельная база данных японско-русского словаря и исходники словарей
JP_DICT_DB_PATH = DATA_DIR / "jp_dict.sqlite"
DICT_SOURCES_DIR = DATA_DIR / "dictionaries"
DICT_SOURCES_DIR.mkdir(parents=True, exist_ok=True)

# 2. Папка для весов моделей (.pt, .onnx, чекпоинты)
WEIGHTS_DIR = BASE_DIR / "weights"
WEIGHTS_DIR.mkdir(exist_ok=True)

# Кэш моделей (чтобы MangaOCR и Torch не качали всё в C:)
CACHE_DIR = WEIGHTS_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
os.environ["TORCH_HOME"] = str(CACHE_DIR / "torch")
os.environ["YOLO_CONFIG_DIR"] = str(CACHE_DIR / "ultralytics")

# Онлайн-режим для huggingface/transformers
os.environ["TRANSFORMERS_OFFLINE"] = "0"
os.environ["HF_HUB_OFFLINE"] = "0"

# Папки стандартных моделей: детекция баблов и клин (LaMa)
DETECT_MODELS_DIR = WEIGHTS_DIR / "detect-bubble"
DETECT_MODELS_DIR.mkdir(parents=True, exist_ok=True)

CLEAN_MODELS_DIR = WEIGHTS_DIR / "clean-lama"
CLEAN_MODELS_DIR.mkdir(parents=True, exist_ok=True)

OCR_MODELS_DIR = WEIGHTS_DIR / "ocr"
OCR_MODELS_DIR.mkdir(parents=True, exist_ok=True)

YOLO_WEIGHTS_PATH = WEIGHTS_DIR / "yolo_manga.pt"
if not YOLO_WEIGHTS_PATH.exists() and (BASE_DIR / "yolo_manga.pt").exists():
    YOLO_WEIGHTS_PATH = BASE_DIR / "yolo_manga.pt"

if not DB_PATH.exists() and (BASE_DIR / "manga_db.sqlite").exists():
    DB_PATH = BASE_DIR / "manga_db.sqlite"


def get_available_detectors() -> Dict[str, str]:
    """Сканирует weights/detect-bubble/*.pt и weights/*.pt."""
    detectors: Dict[str, str] = {}
    bubble_pt_files = sorted(list(DETECT_MODELS_DIR.glob("*.pt")), key=lambda p: p.name.lower())
    for f in bubble_pt_files:
        detectors[f.name] = f.name

    if not detectors:
        root_weights_pt = sorted(list(WEIGHTS_DIR.glob("*.pt")), key=lambda p: p.name.lower())
        for f in root_weights_pt:
            if "lama" not in f.name.lower() and "generator" not in f.name.lower():
                detectors[f.name] = f.name

    if not detectors:
        detectors["yolo_manga.pt"] = "yolo_manga.pt"

    return detectors


def get_available_cleaners() -> Dict[str, str]:
    """Сканирует weights/clean-lama/*.pt и weights/*lama*.pt для моделей Inpainting."""
    cleaners: Dict[str, str] = {}

    lama_files = sorted(list(CLEAN_MODELS_DIR.glob("*.pt")), key=lambda p: p.name.lower())
    for f in lama_files:
        cleaners[f.name] = f.name

    root_lama = sorted(list(WEIGHTS_DIR.glob("*lama*.pt")), key=lambda p: p.name.lower())
    for f in root_lama:
        if f.name not in cleaners:
            cleaners[f.name] = f.name

    if not cleaners:
        cleaners["anime-manga-big-lama.pt"] = "anime-manga-big-lama.pt"

    return cleaners


def get_available_ocr_models() -> Dict[str, str]:
    """
    Сканирует weights/ocr/ на подпапки с весами HuggingFace
    (обязательно: config.json и model.safetensors / pytorch_model.bin).
    """
    ocr_models: Dict[str, str] = {
        "manga-ocr-base": "manga-ocr-base (Default)"
    }

    if OCR_MODELS_DIR.exists():
        subdirs = sorted(
            [d for d in OCR_MODELS_DIR.iterdir() if d.is_dir()],
            key=lambda p: p.name.lower(),
        )
        for d in subdirs:
            has_config = (d / "config.json").exists()
            has_weights = (
                (d / "model.safetensors").exists()
                or (d / "pytorch_model.bin").exists()
                or any(d.glob("model-*.safetensors"))
            )
            if has_config and has_weights:
                ocr_models[d.name] = d.name

    return ocr_models


# Настройки клина
LAMA_FORCE_GRAYSCALE = os.getenv("LAMA_FORCE_GRAYSCALE", "false").lower() in ("true", "1", "yes")
MAX_LAMA_DIM = int(os.getenv("MAX_LAMA_DIM", "2048"))


def natural_sort_key(s: str) -> List[object]:
    """Ключ натуральной сортировки строк с числами (например, 'Page 2' перед 'Page 10')."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

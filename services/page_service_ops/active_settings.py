# services/page_service_ops/active_settings.py
# Чтение актуальных настроек приложения из таблицы global_settings

import threading
from typing import Any, Dict, Optional

from database import get_db

# Настройки читаются на каждый /analyze, /ocr и клин (десятки раз при открытии
# JP-плашек), поэтому держим их в потокобезопасном кэше до записи настроек.
_settings_lock = threading.Lock()
_cached_settings: Optional[Dict[str, Any]] = None

_DEFAULT_SETTINGS: Dict[str, Any] = {
    "detector_model": "yolo_manga.pt",
    "ocr_model": "manga-ocr-base",
    "clean_model": "anime-manga-big-lama.pt",
    "detect_conf": 0.25,
    "auto_oval_bubble": 1,
    "default_padding": "safe",
    "default_hyphenation": 1,
    "font_bubble": "v_CCFaceFront",
    "font_thought": "v_CCFaceFront",
    "font_sfx": "v_Mighty Zeo 2.0",
    "lama_downscale": 0,
    "show_sfx": 0,
    "export_format": "png",
    "brush_model": "opencv",
    "brush_threshold": 0.5,
    "brush_extra_dilate": 0,
    "brush_max_side": 512,
}


def invalidate_global_settings_cache() -> None:
    """Сбрасывает кэш настроек после записи (вызывается из update-эндпоинта)."""
    global _cached_settings
    with _settings_lock:
        _cached_settings = None


def get_active_global_settings() -> Dict[str, Any]:
    global _cached_settings

    # Быстрый путь без лока: словарь заменяется атомарно целиком.
    cached = _cached_settings
    if cached is not None:
        return dict(cached)

    with _settings_lock:
        if _cached_settings is not None:
            return dict(_cached_settings)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM global_settings WHERE id = 1")
            row = cur.fetchone()

        settings = dict(row) if row else dict(_DEFAULT_SETTINGS)
        _cached_settings = settings
        return dict(settings)

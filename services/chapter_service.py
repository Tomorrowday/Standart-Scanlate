# services/chapter_service.py
"""
Сервис глав манги: экспорт в JSON-скрипты, умный импорт переводов и управление кеглем.
Зависимости: os, json, re, pathlib, database, services.prompts, logger
"""

from typing import Dict, Any, Tuple, Optional
from services.chapter_service_ops import (
    CLASS_ID_TO_TYPE,
    apply_font_size_to_chapter_service,
    build_chapter_export_payloads,
    export_chapter_dialogue_to_folder,
    find_latest_dialogue_json_in_folder,
    get_chapter_folder_path,
    import_chapter_dialogue_payload,
)

__all__ = [
    "CLASS_ID_TO_TYPE",
    "build_chapter_export_payloads",
    "export_chapter_dialogue_to_folder",
    "get_chapter_folder_path",
    "find_latest_dialogue_json_in_folder",
    "apply_font_size_to_chapter_service",
    "import_chapter_dialogue_payload",
]
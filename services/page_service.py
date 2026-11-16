# services/page_service.py
"""
Сервис страницы: сохранение баблов, автодетект, клин и откат.
Зависимости: os, time, uuid, pathlib, PIL, database, schemas.TextBlockItem,
                    services.cleaner, services.detector, services.ocr, logger
"""

from typing import List, Dict, Any, Tuple, Optional
from schemas import TextBlockItem
from services.page_service_ops import (
    clean_page_bubbles_service,
    detect_page_bubbles_service,
    get_active_global_settings,
    revert_page_clean_service,
    save_page_blocks_service,
)

__all__ = [
    "get_active_global_settings",
    "save_page_blocks_service",
    "detect_page_bubbles_service",
    "clean_page_bubbles_service",
    "revert_page_clean_service",
]
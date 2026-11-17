# routers/ai_handlers/__init__.py
# Пакет обработчиков AI-роутера: OCR области бабла и перевод реплик

from routers.ai_handlers.ocr_endpoint import perform_ocr
from routers.ai_handlers.translate_endpoints import (
    translate_batch_endpoint,
    translate_batch_stub,
    translate_text_endpoint,
    translate_text_stub,
)

__all__ = [
    "perform_ocr",
    "translate_text_endpoint",
    "translate_batch_endpoint",
    "translate_text_stub",
    "translate_batch_stub",
]

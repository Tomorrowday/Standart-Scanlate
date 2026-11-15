# routers/ai.py
"""
Каркас роутера AI (MangaOCR распознавание и перевод через Gemini / локальную Ollama).
Реализация: routers/ai_impl.py
Зависимости реализации: os, threading, PIL, database.get_db, schemas.OcrRequest, services.ocr.ocr_image_region
"""

from fastapi import APIRouter
from schemas import OcrRequest, TranslationRequest, BatchTranslationRequest
import routers.ai_impl as _impl

router = APIRouter(prefix="/api", tags=["AI"])


@router.post("/ocr")
def perform_ocr(req: OcrRequest):
    """Распознавание японского текста (MangaOCR) по координатам с учётом угла поворота (выполняется в threadpool)."""
    return _impl.perform_ocr(req)


@router.post("/translate")
def translate_text(req: TranslationRequest):
    """Одиночный перевод реплики через Gemini или локальную Ollama."""
    return _impl.translate_text_endpoint(req)


@router.post("/translate/batch")
def translate_batch(req: BatchTranslationRequest):
    """Пакетный перевод реплик страницы с подгрузкой синопсиса и глоссария тайтла."""
    return _impl.translate_batch_endpoint(req)

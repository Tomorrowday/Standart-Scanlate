# routers/ai.py
"""
Роутер AI (MangaOCR распознавание и перевод через Gemini / локальную Ollama).
Зависимости: os, threading, PIL, database.get_db, schemas.OcrRequest, services.ocr.ocr_image_region
"""

from fastapi import APIRouter
from schemas import OcrRequest, TranslationRequest, BatchTranslationRequest
from routers import ai_handlers as _h

router = APIRouter(prefix="/api", tags=["AI"])


@router.post("/ocr")
def perform_ocr(req: OcrRequest):
    """Распознавание японского текста (MangaOCR) по координатам с учётом угла поворота (выполняется в threadpool)."""
    return _h.perform_ocr(req)


@router.post("/translate")
def translate_text(req: TranslationRequest):
    """Одиночный перевод реплики через Gemini или локальную Ollama."""
    return _h.translate_text_endpoint(req)


@router.post("/translate/batch")
def translate_batch(req: BatchTranslationRequest):
    """Пакетный перевод реплик страницы с подгрузкой синопсиса и глоссария тайтла."""
    return _h.translate_batch_endpoint(req)


@router.get("/ollama/status")
def ollama_status():
    """Статус локальной Ollama (модели, выбранная чат-модель) для UI."""
    from services.translator_ops.ollama import list_ollama_models, pick_chat_model

    try:
        models = list_ollama_models()
        return {
            "ok": True,
            "models": models,
            "selected_model": pick_chat_model(models) if models else None,
        }
    except Exception as e:
        return {"ok": False, "models": [], "selected_model": None, "error": str(e)}

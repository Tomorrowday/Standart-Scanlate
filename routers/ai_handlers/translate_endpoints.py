# routers/ai_handlers/translate_endpoints.py
# Одиночный и пакетный перевод реплик через Gemini или локальную Ollama

from typing import Any, Dict, List

from database import get_db
from schemas import TranslationRequest, BatchTranslationRequest
from ml.models import ml
from services.translator import translate_single_text, translate_batch_items
from routers.chapters_handlers.translate_chapter import _translate_chapter_via_ollama


def translate_text_endpoint(req: TranslationRequest):
    """Одиночный перевод реплики через Gemini или локальную Ollama."""
    text = (req.text or "").strip()
    if not text:
        return {"success": True, "translated": ""}

    try:
        if ml.gemini_model:
            translated = translate_single_text(text, req.title_description or "")
        else:
            glossary_rows = [
                {"jap_word": k, "rus_word": v, "context": ""}
                for k, v in (req.glossary or {}).items()
            ]
            res_map = _translate_chapter_via_ollama(
                [{"id": "single", "text": text, "speaker": "", "class_id": 0}],
                title_description=req.title_description or req.context or "",
                glossary_rows=glossary_rows,
            )
            translated = res_map.get("single", "")
        return {"success": True, "translated": translated}
    except Exception as e:
        return {"success": False, "error": str(e)}


def translate_batch_endpoint(req: BatchTranslationRequest):
    """Пакетный перевод реплик страницы с автоматической подгрузкой глоссария и синопсиса тайтла по page_id."""
    if not req.items:
        return {"success": True, "translations": {}}

    title_desc = (req.title_description or "").strip()
    glossary_rows: List[Dict[str, Any]] = []

    if req.page_id:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT t.id as title_id, t.description
                FROM pages p
                JOIN chapters c ON c.id = p.chapter_id
                JOIN titles t ON t.id = c.title_id
                WHERE p.id = ?
                """,
                (req.page_id,),
            )
            t_row = cur.fetchone()
            if t_row:
                if not title_desc:
                    title_desc = t_row["description"] or ""
                cur.execute(
                    "SELECT jap_word, rus_word, context FROM glossary WHERE title_id = ?",
                    (t_row["title_id"],),
                )
                glossary_rows = [dict(r) for r in cur.fetchall()]

    try:
        if ml.gemini_model:
            translations = translate_batch_items(req.items, title_desc, glossary_rows)
        else:
            dialogue_items = [
                {
                    "id": it.id,
                    "text": it.text,
                    "speaker": it.speaker or "",
                    "class_id": it.class_id or 0,
                }
                for it in req.items
            ]
            translations = _translate_chapter_via_ollama(
                dialogue_items,
                title_description=title_desc,
                glossary_rows=glossary_rows,
            )
        return {"success": True, "translations": translations}
    except Exception as e:
        return {"success": False, "error": str(e), "translations": {}}


# Алиасы на случай внешних вызовов старых имён
translate_text_stub = translate_text_endpoint
translate_batch_stub = translate_batch_endpoint

__all__ = [
    "translate_text_endpoint",
    "translate_batch_endpoint",
    "translate_text_stub",
    "translate_batch_stub",
]

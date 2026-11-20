# routers/ai_handlers/translate_endpoints.py
# Одиночный и пакетный перевод реплик через локальную Ollama

from typing import Any, Dict, List

from fastapi import HTTPException

from database import get_db
from schemas import TranslationRequest, BatchTranslationRequest
from services.translator_ops.ollama import translate_via_ollama as _translate_chapter_via_ollama


def translate_text_endpoint(req: TranslationRequest):
    """Одиночный перевод реплики через локальную Ollama."""
    text = (req.text or "").strip()
    if not text:
        return {"success": True, "translated": ""}

    try:
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
        raise HTTPException(status_code=502, detail=str(e))


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
        raise HTTPException(status_code=502, detail=str(e))


# Алиасы на случай внешних вызовов старых имён
translate_text_stub = translate_text_endpoint
translate_batch_stub = translate_batch_endpoint

__all__ = [
    "translate_text_endpoint",
    "translate_batch_endpoint",
    "translate_text_stub",
    "translate_batch_stub",
]

from typing import Dict, Any, List
from fastapi import HTTPException

from database import db_session, get_db
from services.translator_ops.ollama import translate_via_ollama
from logger import logger

CLASS_TYPE_LABELS = {
    0: "bubble",
    1: "thought",
    2: "text",
    3: "sfx",
}


def _translate_chapter_via_ollama(
    dialogue_items: List[Dict[str, Any]],
    title_description: str = "",
    glossary_rows: List[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Локальный перевод главы через Ollama (общий сервис, чанками)."""
    return translate_via_ollama(dialogue_items, title_description, glossary_rows)


def translate_chapter_endpoint(chapter_id: int):
    """Переводит все реплики главы через Gemini или локальную Ollama."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.title_id, t.description, g.auto_oval_bubble
            FROM chapters c
            JOIN titles t ON t.id = c.title_id
            LEFT JOIN global_settings g ON g.id = 1
            WHERE c.id = ?
            """,
            (chapter_id,)
        )
        ch_row = cur.fetchone()
        if not ch_row:
            raise HTTPException(status_code=404, detail="Глава не найдена")

        title_id = ch_row["title_id"]
        title_desc = ch_row["description"] or ""
        auto_oval = bool(ch_row["auto_oval_bubble"]) if ch_row["auto_oval_bubble"] is not None else True

        cur.execute("SELECT jap_word, rus_word, context FROM glossary WHERE title_id = ?", (title_id,))
        glossary_rows = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT tb.id, tb.page_id, tb.jap_text, tb.speaker, tb.class_id, tb.shape, p.page_number
            FROM text_blocks tb
            JOIN pages p ON p.id = tb.page_id
            WHERE p.chapter_id = ? AND TRIM(tb.jap_text) != ''
            ORDER BY p.page_number ASC, tb.order_index ASC
            """,
            (chapter_id,)
        )
        blocks = [dict(r) for r in cur.fetchall()]

    if not blocks:
        return {
            "success": True,
            "updated_count": 0,
            "updated_page_ids": [],
            "message": "Нет распознанных японских реплик для перевода.",
        }

    chapter_dialogue = [
        {
            "id": b["id"],
            "page": b["page_number"],
            "speaker": b["speaker"] or "",
            "text": b["jap_text"],
            "class_id": b.get("class_id", 0),
            "type": CLASS_TYPE_LABELS.get(int(b.get("class_id") or 0), "bubble"),
        }
        for b in blocks
    ]

    try:
        translations = _translate_chapter_via_ollama(chapter_dialogue, title_desc, glossary_rows)
    except Exception as e:
        logger.error(f"Ошибка при пакетном переводе главы {chapter_id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=(
                f"Не удалось выполнить автоматический перевод главы ({e}). "
                "Запустите локальную Ollama или используйте Export JSON / Import JSON."
            ),
        )

    updated_count = 0
    updated_page_ids: set[int] = set()
    with db_session() as cur:
        for b in blocks:
            b_id = b["id"]
            trans_text = translations.get(b_id, "").strip()
            if not trans_text:
                continue

            new_shape = b.get("shape") or "rect"
            if int(b.get("class_id") or 0) == 0 and auto_oval:
                new_shape = "ellipse"

            cur.execute(
                """
                UPDATE text_blocks
                SET rus_text = ?, shape = ?, status = 'translated'
                WHERE id = ?
                """,
                (trans_text, new_shape, b_id)
            )
            updated_count += 1
            updated_page_ids.add(int(b["page_id"]))

        # Статус `translated` ставим только страницам, где реально появился перевод.
        if updated_page_ids:
            placeholders = ",".join("?" for _ in updated_page_ids)
            cur.execute(
                f"""
                UPDATE pages
                SET status = 'translated'
                WHERE id IN ({placeholders}) AND status != 'done'
                """,
                tuple(updated_page_ids)
            )

    return {
        "success": True,
        "updated_count": updated_count,
        "updated_page_ids": sorted(updated_page_ids),
        "message": f"Переведено {updated_count} из {len(blocks)} реплик главы.",
    }

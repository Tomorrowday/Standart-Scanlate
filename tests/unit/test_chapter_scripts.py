# tests/unit/test_chapter_scripts.py
# Экспорт/импорт JSON-скриптов главы и безопасный Content-Disposition.

import json

import pytest

from database import db_session, get_db
from routers.chapters_handlers.dialogue_scripts import _build_attachment_header
from services.chapter_service_ops.export_payloads import build_chapter_export_payloads
from services.chapter_service_ops.import_payloads import import_chapter_dialogue_payload

pytestmark = pytest.mark.unit


def _insert_page(chapter_id: int, page_number: int, file_path: str) -> int:
    with db_session() as cur:
        cur.execute(
            "INSERT INTO pages (chapter_id, page_number, file_path) VALUES (?, ?, ?)",
            (chapter_id, page_number, file_path),
        )
        return int(cur.lastrowid)


def test_build_chapter_export_payloads_matches_page_order_and_types(
    make_title, make_chapter, insert_block, tmp_path
):
    title_id = make_title(name="Манга: Том / 1", folder_path=str(tmp_path))
    chapter_id = make_chapter(title_id=title_id, chapter_number="2", folder_path=str(tmp_path))

    with db_session() as cur:
        cur.execute(
            "INSERT INTO glossary (title_id, jap_word, rus_word, context) VALUES (?, ?, ?, ?)",
            (title_id, "東京", "Токио", "город"),
        )
    with db_session() as cur:
        cur.execute("UPDATE titles SET description = 'Синопсис' WHERE id = ?", (title_id,))

    p1 = _insert_page(chapter_id, 1, str(tmp_path / "001.png"))
    p2 = _insert_page(chapter_id, 2, str(tmp_path / "002.png"))

    insert_block(p1, "b1", class_id=0, order_index=2, jap_text="あ", rus_text="А", speaker="A")
    insert_block(p1, "b2", class_id=2, order_index=0, jap_text="い", rus_text="Б")
    insert_block(p2, "b3", class_id=3, order_index=5, jap_text="う", rus_text="В")

    context_json, dialogues_json, context_name, dialogues_name, folder = build_chapter_export_payloads(
        chapter_id
    )

    dialogues = json.loads(dialogues_json)
    # Блок без order_index идёт первым по page_number/order_index и получает
    # порядковый номер-фоллбэк 1; следующий блок сохраняет свой order_index=2.
    assert [d["id"] for d in dialogues] == ["1-1", "1-2", "2-5"]
    assert [d["type"] for d in dialogues] == ["text", "bubble", "sfx"]
    assert dialogues[0]["raw"] == "い"
    assert dialogues[0]["ru"] == "Б"
    assert dialogues[1]["raw"] == "あ"
    assert dialogues[1]["ru"] == "А"
    assert dialogues[2]["speaker"] == ""

    context = json.loads(context_json)
    assert context["synopsis"] == "Синопсис"
    assert context["glossary"] == [{"jap": "東京", "rus": "Токио", "context": "город"}]

    assert folder == str(tmp_path)
    assert dialogues_name.endswith("_dialogues.json")
    assert context_name.endswith("_context.json")
    assert not any(ch in dialogues_name for ch in '\\/*?:"<>|')


def test_import_dialogue_matches_by_page_order_and_uuid(make_title, make_chapter, make_page, insert_block):
    title_id = make_title()
    chapter_id = make_chapter(title_id=title_id)
    page1 = make_page(chapter_id, page_number=1)
    page2 = make_page(chapter_id, page_number=2)
    page3 = make_page(chapter_id, page_number=3)

    a_id = insert_block(page1, "aaaa-1111", class_id=0, order_index=1, rus_text="", speaker="")
    insert_block(page1, "bbbb-2222", class_id=1, order_index=2, rus_text="", speaker="")
    c_id = insert_block(page2, "cccc-3333", class_id=0, order_index=1, rus_text="", speaker="")
    insert_block(page3, "dddd-4444", class_id=0, order_index=1, rus_text="", speaker="")

    with db_session() as cur:
        cur.execute("UPDATE pages SET status = 'done' WHERE id = ?", (page2,))
        cur.execute("UPDATE pages SET status = 'detected' WHERE id = ?", (page3,))

    payload = [
        {"id": "1-1", "ru": "Первый перевод", "speaker": None},
        {"id": "bbbb-2222", "ru": None, "speaker": "Макима"},
        {"id": "2-1", "ru": "Готовый текст", "speaker": None},
        {"id": "unknown-id", "ru": "Игнор", "speaker": None},
    ]
    res = import_chapter_dialogue_payload(
        chapter_id, json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )

    assert res["updated_count"] == 3
    assert res["updated_speakers_count"] == 1
    assert res["total_records"] == 4
    assert res["updated_page_ids"] == sorted([page1, page2])

    with get_db() as conn:
        rows = {
            row["id"]: dict(row)
            for row in conn.execute(
                "SELECT id, rus_text, speaker, shape, status FROM text_blocks"
            ).fetchall()
        }
        pages = {
            row["id"]: row["status"]
            for row in conn.execute("SELECT id, status FROM pages").fetchall()
        }

    assert rows[a_id]["rus_text"] == "Первый перевод"
    # auto_oval_bubble=1: бабл речи (0) с переводом становится овалом.
    assert rows[a_id]["shape"] == "ellipse"
    assert rows[a_id]["status"] == "translated"
    # UUID-матчинг, null в ru не затирает существующий текст, спикер обновляется.
    assert rows["bbbb-2222"]["speaker"] == "Макима"
    assert rows["bbbb-2222"]["status"] == "ocr-done"
    # Статус done не понижается даже после записи перевода.
    assert pages[page2] == "done"
    # Незатронутая страница остаётся detected.
    assert pages[page3] == "detected"

    with get_db() as conn:
        block_c = conn.execute(
            "SELECT rus_text, status FROM text_blocks WHERE id = ?", (c_id,)
        ).fetchone()
    assert block_c["rus_text"] == "Готовый текст"


def test_import_dialogue_respects_disabled_auto_oval(
    make_title, make_chapter, make_page, insert_block
):
    title_id = make_title()
    chapter_id = make_chapter(title_id=title_id)
    page = make_page(chapter_id, page_number=1)
    block_id = insert_block(page, "block-oval", class_id=0, order_index=1, shape="rect")

    with db_session() as cur:
        cur.execute("UPDATE global_settings SET auto_oval_bubble = 0 WHERE id = 1")

    payload = json.dumps([{"id": "1-1", "ru": "Текст"}]).encode("utf-8")
    import_chapter_dialogue_payload(chapter_id, payload)

    with get_db() as conn:
        row = conn.execute("SELECT shape FROM text_blocks WHERE id = ?", (block_id,)).fetchone()
    assert row["shape"] == "rect"


def test_import_dialogue_accepts_code_fence_and_dict_payload(make_title, make_chapter, make_page, insert_block):
    chapter_id = make_chapter(title_id=make_title())
    page = make_page(chapter_id, page_number=1)
    insert_block(page, "block-fence", order_index=1)

    raw = "```json\n" + json.dumps({"dialogues": [{"id": "1-1", "ru": "Из блока"}]}) + "\n```"
    res = import_chapter_dialogue_payload(chapter_id, raw.encode("utf-8"))
    assert res["updated_count"] == 1


def test_build_attachment_header_supports_cyrillic_and_blocks_injection():
    header = _build_attachment_header("Глава_1_dialogues.json")

    assert header.startswith("attachment;")
    assert 'filename="' in header
    assert "filename*=UTF-8''" in header
    assert "%D0%93" in header  # UTF-8 percent-encoding кириллицы

    malicious = _build_attachment_header('bad\r\nX-Injected: 1"\nname.json')
    assert "\r" not in malicious
    assert "\n" not in malicious
    assert malicious.startswith("attachment;")
    # Заголовок остаётся одной строкой: инъекция новой строки невозможна.
    assert "filename*=UTF-8''" in malicious


def test_build_attachment_header_uses_fallback_for_empty_name():
    header = _build_attachment_header("   ")
    assert 'filename="dialogues.json"' in header

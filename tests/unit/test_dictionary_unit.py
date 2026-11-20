# tests/unit/test_dictionary_unit.py
# Деинфлексия, импорт Yomitan ZIP во временную БД и приоритет терминов глоссария.

import json
import sqlite3
import zipfile

import pytest

from database import db_session
from services.dictionary_ops.analyzer import MangaDictionaryEngine
from services.dictionary_ops.deinflector import (
    collapse_manga_emphasis,
    deinflect_candidates,
    kata_to_hira,
)
from services.dictionary_ops.yomitan_importer import extract_plain_senses, import_yomitan_zip

pytestmark = pytest.mark.unit


def test_kata_to_hira_and_collapse_emphasis():
    assert kata_to_hira("カタカナ") == "かたかな"
    assert kata_to_hira("スーパー") == "すーぱー"
    assert kata_to_hira("") == ""

    assert collapse_manga_emphasis("すっっっごい") == "すっごい"
    assert collapse_manga_emphasis("あああ") == "あ"
    assert collapse_manga_emphasis("スッッゴイ") == "スッゴイ"


def test_deinflect_candidates_standard_past_tense():
    results = deinflect_candidates("食べた")

    assert ("食べる", ["прошедшее время"], ["v1"]) in results
    # Поверхностная форма тоже остаётся кандидатом.
    assert any(word == "食べた" for word, _, _ in results)


def test_deinflect_candidates_handles_katakana_and_elongation():
    results = deinflect_candidates("スゲー")
    words = [w for w, _, _ in results]

    assert "すげー" in words
    assert "スゲ" in words


def test_extract_plain_senses_supports_strings_and_structured_content():
    raw = [
        "простое значение",
        {"type": "text", "text": "текст узла"},
        {"type": "structured-content", "content": ["часть 1", {"content": "часть 2"}]},
        {"type": "image", "path": "x.png"},
        "",
    ]

    assert extract_plain_senses(raw) == [
        "простое значение",
        "текст узла",
        "часть 1 часть 2",
    ]


def _make_mini_yomitan_zip(path) -> None:
    rows = [
        ["東京", "とうきょう", "名詞", "", 100, ["Токио", {"type": "text", "text": "столица"}], 1, ""],
        ["走る", "はしる", "動詞", "v5r", 200, ["бежать"], 2, ""],
    ]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("term_bank_1.json", json.dumps(rows, ensure_ascii=False))


def test_import_yomitan_zip_into_temporary_database(tmp_path):
    zip_path = tmp_path / "mini-yomitan.zip"
    db_path = tmp_path / "jp_dict.sqlite"
    _make_mini_yomitan_zip(zip_path)

    inserted = import_yomitan_zip(zip_path, source_label="test_source", db_path=db_path)

    assert inserted == 2
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT kanji, reading, senses_json FROM dict_entries WHERE source = 'test_source' ORDER BY kanji"
    ).fetchall()
    conn.close()

    assert [r["kanji"] for r in rows] == ["東京", "走る"]
    tokyo_senses = json.loads(rows[0]["senses_json"])
    assert tokyo_senses == ["Токио", "столица"]


def test_import_yomitan_zip_rejects_non_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_text("not a zip", encoding="utf-8")

    with pytest.raises(ValueError):
        import_yomitan_zip(bad, source_label="x", db_path=tmp_path / "dict.sqlite")


def test_find_glossary_intervals_prefers_longest_term(tmp_path, make_title):
    title_id = make_title()
    with db_session() as cur:
        cur.execute(
            "INSERT INTO glossary (title_id, jap_word, rus_word, context) VALUES (?, '東京', 'Токио', '')",
            (title_id,),
        )
        cur.execute(
            "INSERT INTO glossary (title_id, jap_word, rus_word, context) VALUES (?, '東京都', 'Токио (метрополия)', '')",
            (title_id,),
        )

    engine = MangaDictionaryEngine(path := tmp_path / "jp_dict.sqlite")
    hits = engine.find_glossary_intervals("東京都に行く", title_id)

    assert len(hits) == 1
    start, end, hit = hits[0]
    assert (start, end) == (0, 3)
    assert hit.jap_word == "東京都"

    # Более длинный термин выигрывает и при обратном порядке в тексте.
    hits2 = engine.find_glossary_intervals("東京と東京都", title_id)
    assert [(s, e, h.jap_word) for s, e, h in hits2] == [
        (0, 2, "東京"),
        (3, 6, "東京都"),
    ]

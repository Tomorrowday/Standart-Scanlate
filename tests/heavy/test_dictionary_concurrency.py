# tests/heavy/test_dictionary_concurrency.py
# Тяжёлые тесты словаря: многопоточный analyze_bubble и read-only smoke живой базы.

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from services.dictionary_ops.analyzer import MangaDictionaryEngine

pytestmark = pytest.mark.heavy

_REAL_JP_DICT = Path(__file__).resolve().parents[2] / "data" / "jp_dict.sqlite"


def test_analyze_bubble_is_thread_safe(tmp_path):
    engine = MangaDictionaryEngine(tmp_path / "jp_dict.sqlite")
    phrases = [
        "こんにちは、元気ですか？",
        "東京に行きたいです",
        "彼は走っている",
        "すっっごい！",
        "何をしているの？",
        "食べたことがある",
        "ありがとうございます",
        "ちょっと待って",
    ]

    # Прогреваем ленивую инициализацию SudachiPy/GiNZA до параллельного запуска.
    warmup = engine.analyze_bubble("こんにちは", nlp_mode="auto")
    assert isinstance(warmup, list)

    def work(idx: int):
        return engine.analyze_bubble(phrases[idx % len(phrases)], nlp_mode="auto")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, range(48)))

    assert len(results) == 48
    assert all(isinstance(r, list) for r in results)


def test_read_only_smoke_on_real_dictionary_if_present():
    if not _REAL_JP_DICT.exists():
        pytest.skip("Полная база data/jp_dict.sqlite не собрана")

    uri = f"{_REAL_JP_DICT.resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    except sqlite3.OperationalError as exc:
        pytest.skip(f"Не удалось открыть словарь read-only: {exc}")

    try:
        total = conn.execute("SELECT COUNT(*) FROM dict_entries").fetchone()[0]
        if total <= 0:
            pytest.skip("База словаря пуста")
        rows = conn.execute(
            "SELECT kanji, reading, senses_json FROM dict_entries LIMIT 5"
        ).fetchall()
        assert total > 0
        assert len(rows) == 5
    finally:
        conn.close()

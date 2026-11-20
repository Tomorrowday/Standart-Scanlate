# tests/unit/test_chapter_timer_and_stats.py
# Таймер главы (heartbeat, зависшие сессии, переключение) и подсчёт реплик/слов.

import pytest

from database import db_session, get_db
from routers.chapters_handlers import chapter_timer
from routers.chapters_handlers.chapter_stats import count_words_in_text, recalculate_chapter_stats

pytestmark = pytest.mark.unit


def _set_timer(chapter_id: int, started: int | None, last_seen: int | None, work: int = 0) -> None:
    with db_session() as cur:
        cur.execute(
            """
            UPDATE chapters
            SET work_seconds = ?, timer_started_at = ?, timer_last_seen_at = ?
            WHERE id = ?
            """,
            (work, started, last_seen, chapter_id),
        )


def _timer(chapter_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT work_seconds, timer_started_at, timer_last_seen_at FROM chapters WHERE id = ?",
            (chapter_id,),
        ).fetchone()
    return dict(row)


def test_start_heartbeat_stop_accumulates_time(make_chapter, monkeypatch):
    chapter_id = make_chapter()

    monkeypatch.setattr(chapter_timer.time, "time", lambda: 1000)
    first = chapter_timer.start_chapter_timer(chapter_id)
    assert first["is_running"] is True
    assert first["current_session_seconds"] == 0

    # Повторный start — это heartbeat, сессия не перезапускается.
    monkeypatch.setattr(chapter_timer.time, "time", lambda: 1030)
    beat = chapter_timer.start_chapter_timer(chapter_id)
    assert beat["current_session_seconds"] == 30
    assert _timer(chapter_id)["timer_started_at"] == 1000

    monkeypatch.setattr(chapter_timer.time, "time", lambda: 1060)
    stopped = chapter_timer.stop_chapter_timer(chapter_id)
    assert stopped["is_running"] is False
    assert stopped["work_seconds"] == 60
    assert stopped["total_seconds"] == 60

    row = _timer(chapter_id)
    assert row["timer_started_at"] is None
    assert row["timer_last_seen_at"] is None


def test_hung_session_closes_only_until_last_heartbeat(make_chapter, monkeypatch):
    chapter_id = make_chapter()
    _set_timer(chapter_id, started=1000, last_seen=1050, work=10)

    monkeypatch.setattr(chapter_timer.time, "time", lambda: 1200)  # 150 c > 90 c
    status = chapter_timer.get_chapter_timer_status(chapter_id)

    assert status["is_running"] is False
    assert status["work_seconds"] == 60  # 10 + (1050 - 1000), без простоя до 1200
    assert status["total_seconds"] == 60
    assert _timer(chapter_id)["timer_started_at"] is None


def test_switching_chapter_closes_live_and_stale_sessions(make_chapter, monkeypatch):
    fresh_id = make_chapter(chapter_number="A")
    hung_id = make_chapter(chapter_number="B")
    target_id = make_chapter(chapter_number="C")

    # A: heartbeat 5 c назад -> живую сессию закрываем «до now».
    _set_timer(fresh_id, started=1000, last_seen=1195)
    # B: heartbeat 150 c назад -> зависшую закрываем строго до last_seen.
    _set_timer(hung_id, started=1000, last_seen=1050)

    monkeypatch.setattr(chapter_timer.time, "time", lambda: 1200)
    chapter_timer.start_chapter_timer(target_id)

    fresh = _timer(fresh_id)
    hung = _timer(hung_id)
    assert fresh["work_seconds"] == 200  # now 1200 - started 1000
    assert fresh["timer_started_at"] is None
    assert hung["work_seconds"] == 50  # last_seen 1050 - started 1000
    assert hung["timer_started_at"] is None

    target = _timer(target_id)
    assert target["timer_started_at"] == 1200


def test_stop_timer_is_idempotent_for_deleted_chapter(make_chapter):
    chapter_id = make_chapter()
    with db_session() as cur:
        cur.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))

    result = chapter_timer.stop_chapter_timer(chapter_id)

    assert result["success"] is True
    assert result["deleted"] is True
    assert result["is_running"] is False
    assert result["total_seconds"] == 0


def test_count_words_in_text():
    assert count_words_in_text("") == 0
    assert count_words_in_text("   ") == 0
    assert count_words_in_text("Привет, мир!") == 2
    assert count_words_in_text("Ёжик-ёжик и 42") == 3
    assert count_words_in_text("слово—слово; ещё… тест") == 4


def test_recalculate_chapter_stats_updates_cached_columns(
    make_title, make_chapter, make_page, insert_block
):
    title_id = make_title()
    chapter_id = make_chapter(title_id=title_id)
    page = make_page(chapter_id, page_number=1)

    insert_block(page, "s1", order_index=1, rus_text="Привет мир")
    insert_block(page, "s2", order_index=2, rus_text="  ")
    insert_block(page, "s3", order_index=3, rus_text="Ещё две реплики")
    # Страница другой главы не должна попасть в статистику.
    other_chapter = make_chapter(title_id=title_id, chapter_number="2")
    other_page = make_page(other_chapter, page_number=1)
    insert_block(other_page, "s4", order_index=1, rus_text="Чужая глава")

    res = recalculate_chapter_stats(chapter_id)

    assert res["replicas_count"] == 2
    assert res["words_count"] == 5

    with get_db() as conn:
        row = conn.execute(
            "SELECT cached_replicas_count, cached_words_count FROM chapters WHERE id = ?",
            (chapter_id,),
        ).fetchone()
    assert row["cached_replicas_count"] == 2
    assert row["cached_words_count"] == 5

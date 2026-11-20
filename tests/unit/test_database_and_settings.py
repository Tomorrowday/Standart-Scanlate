# tests/unit/test_database_and_settings.py
# Быстрые тесты инициализации БД, безопасных миграций и настроек приложения.

import sqlite3

import pytest

import database
from schemas import UpdateTitleSettingsRequest
from services.page_service_ops.active_settings import (
    get_active_global_settings,
    invalidate_global_settings_cache,
)

pytestmark = pytest.mark.unit


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_init_db_is_idempotent():
    database.init_db()
    database.init_db()

    with database.get_db() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"global_settings", "titles", "chapters", "pages", "text_blocks", "glossary"} <= tables
        assert conn.execute("SELECT COUNT(*) FROM global_settings WHERE id = 1").fetchone()[0] == 1


def test_safe_migration_adds_missing_columns(tmp_path, monkeypatch):
    old_db = tmp_path / "old_manga_db.sqlite"
    conn = sqlite3.connect(old_db)
    conn.execute(
        """
        CREATE TABLE global_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            default_font_size INTEGER DEFAULT 14,
            detector_model TEXT DEFAULT 'yolo_manga.pt',
            clean_model TEXT DEFAULT 'anime-manga-big-lama.pt',
            detect_conf REAL DEFAULT 0.25,
            auto_oval_bubble INTEGER DEFAULT 1,
            default_padding TEXT DEFAULT 'safe',
            default_hyphenation INTEGER DEFAULT 1,
            font_bubble TEXT DEFAULT 'v_CCFaceFront',
            font_thought TEXT DEFAULT 'v_CCFaceFront',
            font_sfx TEXT DEFAULT 'v_Mighty Zeo 2.0'
        )
        """
    )
    conn.execute("INSERT INTO global_settings (id, default_font_size) VALUES (1, 14)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", old_db)
    database.init_db()

    with database.get_db() as conn:
        columns = _table_columns(conn, "global_settings")
    assert {
        "lama_downscale",
        "show_sfx",
        "dict_nlp_mode",
        "ocr_model",
        "export_format",
        "brush_model",
        "brush_threshold",
        "brush_extra_dilate",
        "brush_max_side",
    } <= columns


def test_init_db_closes_hung_timer_sessions(make_title):
    from database import db_session

    title_id = make_title()
    with db_session() as cur:
        cur.execute(
            """
            INSERT INTO chapters
                (title_id, chapter_number, work_seconds, timer_started_at, timer_last_seen_at)
            VALUES (?, '1', 5, 1000, 1300)
            """,
            (title_id,),
        )
        chapter_id = int(cur.lastrowid)

    database.init_db()

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT work_seconds, timer_started_at, timer_last_seen_at FROM chapters WHERE id = ?",
            (chapter_id,),
        ).fetchone()
    assert row["work_seconds"] == 305  # 5 + (1300 - 1000): только до последнего heartbeat
    assert row["timer_started_at"] is None
    assert row["timer_last_seen_at"] is None


def test_partial_settings_update_preserves_other_fields_and_invalidates_cache():
    from routers.projects_handlers.global_settings import update_global_settings_endpoint

    invalidate_global_settings_cache()
    before = get_active_global_settings()
    assert int(before["default_font_size"]) == 14

    update_global_settings_endpoint(
        UpdateTitleSettingsRequest(font_bubble="Betina Script", detect_conf=0.42)
    )
    after = get_active_global_settings()

    assert after["font_bubble"] == "Betina Script"
    assert float(after["detect_conf"]) == pytest.approx(0.42)
    # Поля, которые не передавались, обязаны сохраниться.
    assert after["font_sfx"] == before["font_sfx"]
    assert int(after["default_font_size"]) == int(before["default_font_size"])

    # Точечное обновление не должно сбрасывать ранее изменённые поля.
    update_global_settings_endpoint(UpdateTitleSettingsRequest(font_thought="v_Augie"))
    final = get_active_global_settings()
    assert final["font_bubble"] == "Betina Script"
    assert final["font_thought"] == "v_Augie"
    assert float(final["detect_conf"]) == pytest.approx(0.42)


def test_brush_settings_are_clamped_and_max_side_is_multiple_of_32():
    from routers.projects_handlers.global_settings import update_global_settings_endpoint

    res = update_global_settings_endpoint(
        UpdateTitleSettingsRequest(
            brush_threshold=5.0,
            brush_extra_dilate=999,
            brush_max_side=500,
        )
    )
    settings = res["settings"]
    assert settings["brush_threshold"] == pytest.approx(0.9)
    assert settings["brush_extra_dilate"] == 16
    assert settings["brush_max_side"] == 512
    assert settings["brush_max_side"] % 32 == 0

    res = update_global_settings_endpoint(
        UpdateTitleSettingsRequest(
            brush_threshold=-3.0,
            brush_extra_dilate=-999,
            brush_max_side=10,
        )
    )
    settings = res["settings"]
    assert settings["brush_threshold"] == pytest.approx(0.1)
    assert settings["brush_extra_dilate"] == -8
    assert settings["brush_max_side"] == 128


def test_get_active_global_settings_reads_database_and_caches():
    invalidate_global_settings_cache()
    first = get_active_global_settings()
    second = get_active_global_settings()
    assert first == second
    assert first["export_format"] == "png"

    # Кэш возвращает копию: порча словаря не влияет на следующие чтения.
    first["export_format"] = "avif"
    assert get_active_global_settings()["export_format"] == "png"

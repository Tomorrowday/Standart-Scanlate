# services/dictionary_ops/jp_dict_db.py
# Подключение к data/jp_dict.sqlite, схема, стартовое заполнение и статус базы словаря

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Iterator, Tuple

from config import JP_DICT_DB_PATH, DICT_SOURCES_DIR
from logger import logger
from services.dictionary_ops.starter_data import STARTER_MANGA_ENTRIES

_build_lock = threading.Lock()
_schema_lock = threading.Lock()

# Версия базы словаря: инкрементируется после пересборки, чтобы thread-local
# read-only соединения не держали устаревший снапшот.
_dict_version = 0
_dict_version_lock = threading.Lock()
_read_conn_local = threading.local()
_build_progress: Dict[str, Any] = {
    "is_building": False,
    "stage": "idle",
    "message": "",
    "error": None,
}


def get_dict_db_connection(db_path: Path = JP_DICT_DB_PATH) -> sqlite3.Connection:
    """Создаёт соединение с базой словаря с настроенными PRAGMA (WAL, mmap, кэш)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA mmap_size = 268435456;")
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA temp_store = 2;")
    return conn


def bump_dict_version() -> None:
    """Сбрасывает кэш read-only соединений после пересборки словаря."""
    global _dict_version
    with _dict_version_lock:
        _dict_version += 1


def get_readonly_dict_connection(db_path: Path = JP_DICT_DB_PATH) -> sqlite3.Connection:
    """
    Возвращает переиспользуемое read-only соединение для текущего потока.

    Раньше на каждый вызов _query_exact_terms открывалось новое соединение и
    заново выставлялись 5 PRAGMA — 15-40 раз на один бабл. Соединение
    переоткрывается при пересборке словаря (bump_dict_version) или изменении
    файла базы.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mtime_ns = os.stat(db_path).st_mtime_ns
    except OSError:
        mtime_ns = 0

    cache: Dict[str, Tuple[int, int, sqlite3.Connection]] = getattr(
        _read_conn_local, "conns", None
    ) or {}
    _read_conn_local.conns = cache

    key = str(db_path)
    entry = cache.get(key)
    if entry and entry[0] == _dict_version and entry[1] == mtime_ns:
        return entry[2]

    if entry:
        try:
            entry[2].close()
        except Exception:
            pass

    # as_uri() корректно экранирует пробелы, '#', '?' и кириллицу в пути.
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=20.0)
    except sqlite3.OperationalError:
        # WAL-база без доступного -shm не открывается read-only (например,
        # сразу после пересборки) — откатываемся к обычному соединению.
        conn = sqlite3.connect(str(db_path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON;")
    conn.execute("PRAGMA mmap_size = 268435456;")
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA temp_store = 2;")
    cache[key] = (_dict_version, mtime_ns, conn)
    return conn


@contextmanager
def dict_db_connection(db_path: Path = JP_DICT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Контекстный менеджер соединения с базой словаря: гарантированно закрывает его."""
    conn = get_dict_db_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def ensure_jp_dict_schema(db_path: Path = JP_DICT_DB_PATH) -> None:
    """Создаёт таблицы и индексы в data/jp_dict.sqlite и засевает стартовый набор, если база пуста."""
    with _schema_lock:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with dict_db_connection(db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dict_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    seq_id INTEGER,
                    kanji TEXT NOT NULL,
                    reading TEXT NOT NULL,
                    rules TEXT DEFAULT '',
                    pos_tags TEXT DEFAULT '',
                    senses_json TEXT NOT NULL,
                    freq_rank INTEGER DEFAULT 999999,
                    score INTEGER DEFAULT 0
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dict_kanji ON dict_entries(kanji, freq_rank ASC, score DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dict_reading ON dict_entries(reading, freq_rank ASC, score DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dict_source ON dict_entries(source);")

            cur.execute("SELECT COUNT(*) FROM dict_entries")
            count = cur.fetchone()[0]
            if count == 0:
                seed_rows = [
                    (src, seq, k, r, rules, pos, json.dumps(senses, ensure_ascii=False), freq, sc)
                    for src, seq, k, r, rules, pos, senses, freq, sc in STARTER_MANGA_ENTRIES
                ]
                cur.executemany(
                    """
                    INSERT INTO dict_entries
                    (source, seq_id, kanji, reading, rules, pos_tags, senses_json, freq_rank, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    seed_rows,
                )
                conn.commit()


def is_dictionary_building() -> bool:
    """O(1)-проверка флага сборки словаря (без DDL и COUNT(*) по 300k строк)."""
    return bool(_build_progress.get("is_building"))


def get_dictionary_status(db_path: Path = JP_DICT_DB_PATH) -> Dict[str, Any]:
    ensure_jp_dict_schema(db_path)
    counts: Dict[str, int] = {}
    total = 0
    try:
        with dict_db_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM dict_entries GROUP BY source"
            ).fetchall()
            for r in rows:
                counts[r["source"]] = int(r["cnt"])
                total += int(r["cnt"])
    except Exception as e:
        logger.warning(f"Ошибка проверки статуса словаря: {e}")

    local_zips = [f.name for f in DICT_SOURCES_DIR.glob("*.zip")]
    return {
        "db_path": str(db_path),
        "total_entries": total,
        "sources": counts,
        "is_full_dictionary_loaded": (
            counts.get("jmdict_ru", 0) > 5000 and counts.get("warodai", 0) > 5000
        ),
        "local_zip_files": local_zips,
        "build_progress": dict(_build_progress),
    }

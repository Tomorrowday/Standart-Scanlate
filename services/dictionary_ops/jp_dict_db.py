# services/dictionary_ops/jp_dict_db.py
# Подключение к data/jp_dict.sqlite, схема, стартовое заполнение и статус базы словаря

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Iterator

from config import JP_DICT_DB_PATH, DICT_SOURCES_DIR
from logger import logger
from services.dictionary_ops.starter_data import STARTER_MANGA_ENTRIES

_build_lock = threading.Lock()
_schema_lock = threading.Lock()
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

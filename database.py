# database.py
"""
Доступ к локальной базе данных SQLite и паспорт схемы данных.
Зависимости: sqlite3, contextlib, config.DB_PATH

СХЕМА ТАБЛИЦ БАЗЫ ДАННЫХ:
---------------------------------------------------------------------------------------------------
1. global_settings:
   - id INTEGER PRIMARY KEY CHECK (id = 1)
   - default_font_size INTEGER DEFAULT 14
   - detector_model TEXT DEFAULT 'yolo_manga.pt'
   - clean_model TEXT DEFAULT 'anime-manga-big-lama.pt'
   - detect_conf REAL DEFAULT 0.25
   - auto_oval_bubble INTEGER DEFAULT 1
   - default_padding TEXT DEFAULT 'safe'
   - default_hyphenation INTEGER DEFAULT 1
   - font_bubble TEXT DEFAULT 'v_CCFaceFront'
   - font_thought TEXT DEFAULT 'v_CCFaceFront'
   - font_sfx TEXT DEFAULT 'v_Mighty Zeo 2.0'
   - lama_downscale INTEGER DEFAULT 0
   - export_format TEXT DEFAULT 'png' ('png', 'webp', 'avif')

2. titles:
   - id INTEGER PRIMARY KEY AUTOINCREMENT
   - name TEXT NOT NULL
   - folder_path TEXT NOT NULL
   - description TEXT DEFAULT ''
   - default_font_size INTEGER DEFAULT 14
   - detector_model TEXT DEFAULT 'yolo_manga.pt'
   - created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

3. chapters:
   - id INTEGER PRIMARY KEY AUTOINCREMENT
   - title_id INTEGER FK -> titles(id) ON DELETE CASCADE
   - volume_number TEXT DEFAULT '1'
   - chapter_number TEXT NOT NULL
   - folder_path TEXT
   - work_seconds INTEGER DEFAULT 0
   - timer_started_at INTEGER DEFAULT NULL
   - timer_last_seen_at INTEGER DEFAULT NULL (heartbeat активности)

4. pages:
   - id INTEGER PRIMARY KEY AUTOINCREMENT
   - chapter_id INTEGER FK -> chapters(id) ON DELETE CASCADE
   - page_number INTEGER
   - file_path TEXT NOT NULL
   - clean_path TEXT
   - status TEXT DEFAULT 'raw' ('raw', 'new', 'detected', 'cleaned', 'translated', 'done')

5. text_blocks:
   - id TEXT PRIMARY KEY (UUID)
   - page_id INTEGER FK -> pages(id) ON DELETE CASCADE
   - class_id INTEGER DEFAULT 0 (0: Bubble, 1: Thought, 2: Text/SFX)
   - x REAL, y REAL, width REAL, height REAL, rotation REAL DEFAULT 0.0
   - jap_text TEXT DEFAULT '', rus_text TEXT DEFAULT '', speaker TEXT DEFAULT ''
   - order_index INTEGER DEFAULT 0
   - font_size INTEGER (NULL = Auto)
   - font_family TEXT DEFAULT 'v_CCFaceFront'
   - is_bold INTEGER DEFAULT 0, is_italic INTEGER DEFAULT 0, is_uppercase INTEGER DEFAULT 0
   - has_stroke INTEGER DEFAULT 0
   - text_color TEXT DEFAULT 'black' ('black', 'white')
   - shape TEXT DEFAULT 'rect' ('rect', 'ellipse')
   - padding_mode TEXT DEFAULT 'safe' ('safe', 'fit')
   - min_hyphens INTEGER DEFAULT 1
   - status TEXT DEFAULT 'new'

6. glossary:
   - id INTEGER PRIMARY KEY AUTOINCREMENT
   - title_id INTEGER NOT NULL FK -> titles(id) ON DELETE CASCADE
   - jap_word TEXT NOT NULL
   - rus_word TEXT NOT NULL
   - context TEXT DEFAULT ''
---------------------------------------------------------------------------------------------------
"""

import sqlite3
from typing import Iterator
from contextlib import contextmanager
from config import DB_PATH


def _create_connection() -> sqlite3.Connection:
    """Создаёт новое соединение с SQLite (WAL, таймаут, строки-словари, включённые FK)."""
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Контекстный менеджер соединения SQLite: гарантированно закрывает его после выхода."""
    conn = _create_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def db_session():
    """Контекстный менеджер транзакции: авто-commit при успехе, rollback при ошибке."""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_db():
    """Инициализация таблиц, проверка/накатывание миграций и удаление сиротских записей."""
    with db_session() as cursor:
        # Создаём таблицу глобальных настроек приложения
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                default_font_size INTEGER DEFAULT 14,
                detector_model TEXT DEFAULT 'yolo_manga.pt',
                clean_model TEXT DEFAULT 'anime-manga-big-lama.pt',
                ocr_model TEXT DEFAULT 'manga-ocr-base',
                detect_conf REAL DEFAULT 0.25,
                auto_oval_bubble INTEGER DEFAULT 1,
                default_padding TEXT DEFAULT 'safe',
                default_hyphenation INTEGER DEFAULT 1,
                font_bubble TEXT DEFAULT 'v_CCFaceFront',
                font_thought TEXT DEFAULT 'v_CCFaceFront',
                font_sfx TEXT DEFAULT 'v_Mighty Zeo 2.0',
                lama_downscale INTEGER DEFAULT 0,
                show_sfx INTEGER DEFAULT 0,
                dict_nlp_mode TEXT DEFAULT 'auto',
                export_format TEXT DEFAULT 'png'
            )
        ''')

        # Безопасные миграции глобальных настроек для старых баз
        for col_def in [
            "lama_downscale INTEGER DEFAULT 0",
            "show_sfx INTEGER DEFAULT 0",
            "dict_nlp_mode TEXT DEFAULT 'auto'",
            "ocr_model TEXT DEFAULT 'manga-ocr-base'",
            "export_format TEXT DEFAULT 'png'",
        ]:
            try:
                cursor.execute(f"ALTER TABLE global_settings ADD COLUMN {col_def}")
            except Exception:
                pass

        # Гарантируем единственную строку настроек с id=1
        cursor.execute("SELECT COUNT(*) FROM global_settings WHERE id = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO global_settings (
                    id, default_font_size, detector_model, clean_model, ocr_model, detect_conf,
                    auto_oval_bubble, default_padding, default_hyphenation,
                    font_bubble, font_thought, font_sfx, lama_downscale, show_sfx, dict_nlp_mode, export_format
                ) VALUES (1, 14, 'yolo_manga.pt', 'anime-manga-big-lama.pt', 'manga-ocr-base', 0.25, 1, 'safe', 1, 'v_CCFaceFront', 'v_CCFaceFront', 'v_Mighty Zeo 2.0', 0, 0, 'auto', 'png')
            ''')

        # Убираем сломанный простой lama, чтобы LaMa всегда был доступен
        cursor.execute(
            "UPDATE global_settings SET clean_model = 'anime-manga-big-lama.pt' WHERE clean_model = 'simple_lama'"
        )

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS titles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                description TEXT DEFAULT '',
                default_font_size INTEGER DEFAULT 14,
                detector_model TEXT DEFAULT 'yolo_manga.pt',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_id INTEGER,
                volume_number TEXT DEFAULT '1',
                chapter_number TEXT NOT NULL,
                folder_path TEXT,
                work_seconds INTEGER DEFAULT 0,
                timer_started_at INTEGER DEFAULT NULL,
                timer_last_seen_at INTEGER DEFAULT NULL,
                cached_replicas_count INTEGER DEFAULT NULL,
                cached_words_count INTEGER DEFAULT NULL,
                FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE
            )
        ''')

        for col_def in [
            "work_seconds INTEGER DEFAULT 0",
            "timer_started_at INTEGER DEFAULT NULL",
            "timer_last_seen_at INTEGER DEFAULT NULL",
            "cached_replicas_count INTEGER DEFAULT NULL",
            "cached_words_count INTEGER DEFAULT NULL",
        ]:
            try:
                cursor.execute(f"ALTER TABLE chapters ADD COLUMN {col_def}")
            except Exception:
                pass

        # Закрываем сессии таймера, зависшие с прошлого запуска сервера.
        # Засчитываем время только до последнего heartbeat, чтобы закрытый браузер
        # или убитый батник не начислили часы простоя.
        cursor.execute(
            """
            UPDATE chapters
            SET work_seconds = COALESCE(work_seconds, 0)
                    + MAX(0, COALESCE(timer_last_seen_at, timer_started_at) - timer_started_at),
                timer_started_at = NULL,
                timer_last_seen_at = NULL
            WHERE timer_started_at IS NOT NULL
            """
        )

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER,
                page_number INTEGER,
                file_path TEXT NOT NULL,
                clean_path TEXT,
                status TEXT DEFAULT 'raw',
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS text_blocks (
                id TEXT PRIMARY KEY,
                page_id INTEGER,
                class_id INTEGER DEFAULT 0,
                x REAL, y REAL, width REAL, height REAL,
                rotation REAL DEFAULT 0.0,
                jap_text TEXT DEFAULT '',
                rus_text TEXT DEFAULT '',
                speaker TEXT DEFAULT '',
                order_index INTEGER DEFAULT 0,
                font_size INTEGER,
                font_family TEXT DEFAULT 'v_CCFaceFront',
                is_bold INTEGER DEFAULT 0,
                is_italic INTEGER DEFAULT 0,
                is_uppercase INTEGER DEFAULT 0,
                has_stroke INTEGER DEFAULT 0,
                text_color TEXT DEFAULT 'black',
                shape TEXT DEFAULT 'rect',
                padding_mode TEXT DEFAULT 'safe',
                min_hyphens INTEGER DEFAULT 1,
                status TEXT DEFAULT 'new',
                FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS glossary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_id INTEGER NOT NULL,
                jap_word TEXT NOT NULL,
                rus_word TEXT NOT NULL,
                context TEXT DEFAULT '',
                FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE
            )
        ''')

        # Чистим осиротевшие записи: каскадная страховка
        cursor.execute("DELETE FROM text_blocks WHERE page_id NOT IN (SELECT id FROM pages)")
        cursor.execute("DELETE FROM pages WHERE chapter_id NOT IN (SELECT id FROM chapters)")
        cursor.execute("DELETE FROM chapters WHERE title_id NOT IN (SELECT id FROM titles)")

    print("База данных инициализирована (WAL включён), таблицы готовы.")
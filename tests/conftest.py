# tests/conftest.py
# Общая изоляция автотестов от живых баз данных и сброс кэшей между тестами.

import sys
import tempfile
from pathlib import Path

import pytest

# Корень проекта должен быть в sys.path, чтобы тесты запускались из любой папки.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config  # noqa: E402
import database  # noqa: E402

# Запоминаем реальные пути ДО любых подмен: они нужны guard'у и тяжёлому smoke-тесту словаря.
REAL_MANGA_DB_PATH = Path(config.DB_PATH).resolve()
REAL_JP_DICT_DB_PATH = Path(config.JP_DICT_DB_PATH).resolve()

# Модульный singleton словаря (services.dictionary_ops.analyzer.dict_engine) создаётся
# при импорте и связывает путь словаря значением по умолчанию. Перенаправляем словарь
# на сессионную временную папку ДО импорта тестовых модулей, чтобы даже импорт
# services.dictionary не открывал живую data/jp_dict.sqlite.
_SESSION_JP_DICT_DIR = Path(tempfile.mkdtemp(prefix="manga_tests_jp_dict_"))
config.JP_DICT_DB_PATH = _SESSION_JP_DICT_DIR / "jp_dict.sqlite"
config.DICT_SOURCES_DIR = _SESSION_JP_DICT_DIR / "dictionaries"
config.DICT_SOURCES_DIR.mkdir(parents=True, exist_ok=True)


def _assert_not_live_db(path) -> None:
    """Жёсткий guard: тесты не имеют права открывать или перезаписывать живую БД."""
    resolved = Path(path).resolve()
    if resolved == REAL_MANGA_DB_PATH:
        raise AssertionError(
            "ОПАСНО: тест пытается использовать живую data/manga_db.sqlite. "
            "Все тесты обязаны работать только с tmp_path."
        )


@pytest.fixture(autouse=True)
def isolated_manga_db(tmp_path, monkeypatch):
    """
    Перенаправляет рабочую БД на временный файл и инициализирует её перед каждым тестом.

    database.py использует `from config import DB_PATH`, поэтому подменять нужно
    именно атрибут `database.DB_PATH` (и для полноты — `config.DB_PATH`).
    """
    from services.page_service_ops.active_settings import invalidate_global_settings_cache

    temp_db = tmp_path / "manga_db.sqlite"
    _assert_not_live_db(temp_db)

    monkeypatch.setattr(config, "DB_PATH", temp_db)
    monkeypatch.setattr(database, "DB_PATH", temp_db)

    # Кэш настроек мог прогреться предыдущим тестом — начинаем с чистого листа.
    invalidate_global_settings_cache()
    _assert_not_live_db(database.DB_PATH)
    _assert_not_live_db(config.DB_PATH)

    database.init_db()

    # Guard после инициализации: убеждаемся, что никто не подменил путь назад.
    _assert_not_live_db(database.DB_PATH)

    yield

    invalidate_global_settings_cache()
    _assert_not_live_db(database.DB_PATH)


@pytest.fixture
def db():
    """Короткий доступ к временной рабочей БД внутри теста."""
    from database import get_db

    with get_db() as conn:
        yield conn


@pytest.fixture
def make_title():
    """Создаёт тайтл и возвращает его id."""

    def _make(name: str = "Test Title", folder_path: str = "C:/manga/test") -> int:
        from database import db_session

        with db_session() as cur:
            cur.execute(
                "INSERT INTO titles (name, folder_path, description) VALUES (?, ?, '')",
                (name, folder_path),
            )
            return int(cur.lastrowid)

    return _make


@pytest.fixture
def make_chapter(make_title):
    """Создаёт главу (при необходимости вместе с тайтлом)."""

    def _make(title_id: int | None = None, chapter_number: str = "1", folder_path: str | None = None) -> int:
        from database import db_session

        if title_id is None:
            title_id = make_title()
        with db_session() as cur:
            cur.execute(
                "INSERT INTO chapters (title_id, chapter_number, folder_path) VALUES (?, ?, ?)",
                (title_id, chapter_number, folder_path),
            )
            return int(cur.lastrowid)

    return _make


@pytest.fixture
def make_page(make_chapter, tmp_path):
    """Создаёт страницу с реальным (пустым PNG) файлом на диске."""

    def _make(chapter_id: int | None = None, page_number: int = 1, filename: str | None = None) -> int:
        import numpy as np
        from database import db_session
        from services.cleaner_ops.image_io import save_image_cv2

        if chapter_id is None:
            chapter_id = make_chapter()

        page_dir = tmp_path / "manga"
        page_dir.mkdir(parents=True, exist_ok=True)
        file_name = filename or f"{page_number:03d}.png"
        file_path = page_dir / file_name
        if not file_path.exists():
            save_image_cv2(str(file_path), np.full((240, 180, 3), 255, dtype=np.uint8))

        with db_session() as cur:
            cur.execute(
                "INSERT INTO pages (chapter_id, page_number, file_path) VALUES (?, ?, ?)",
                (chapter_id, page_number, str(file_path)),
            )
            return int(cur.lastrowid)

    return _make


@pytest.fixture
def insert_block():
    """Вставляет текстовый блок в страницу и возвращает его UUID/id."""

    def _insert(page_id: int, block_id: str = "block-1", **overrides) -> str:
        from database import db_session

        values = {
            "id": block_id,
            "page_id": page_id,
            "class_id": 0,
            "x": 0.1,
            "y": 0.1,
            "width": 0.3,
            "height": 0.2,
            "rotation": 0.0,
            "jap_text": "",
            "rus_text": "",
            "speaker": "",
            "order_index": 1,
            "font_size": None,
            "font_family": "v_CCFaceFront",
            "is_bold": 0,
            "is_italic": 0,
            "is_uppercase": 0,
            "has_stroke": 0,
            "text_color": "black",
            "shape": "rect",
            "padding_mode": "safe",
            "min_hyphens": 1,
            "status": "new",
        }
        values.update(overrides)
        columns = ", ".join(values.keys())
        placeholders = ", ".join("?" for _ in values)
        with db_session() as cur:
            cur.execute(
                f"INSERT INTO text_blocks ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
        return str(values["id"])

    return _insert

# tests/unit/test_scanner.py
# Натуральная сортировка глав/страниц, обложка, служебные папки и skip_existing.

import pytest

from database import db_session, get_db
from routers.projects_handlers.scanner import (
    EXCLUDED_DIR_NAMES,
    _has_image_subdirs,
    _scan_and_insert_chapters,
)

pytestmark = pytest.mark.unit


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")


def _make_chapter_dir(root, name, page_names):
    folder = root / name
    for page in page_names:
        _touch(folder / page)
    return folder


def _scan(title_id: int, root, **kwargs):
    with db_session() as cur:
        return _scan_and_insert_chapters(cur, title_id, root, **kwargs)


def _chapters(title_id: int):
    with get_db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, chapter_number, folder_path FROM chapters WHERE title_id = ? ORDER BY id",
                (title_id,),
            ).fetchall()
        ]


def _pages(chapter_id: int):
    with get_db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT page_number, file_path FROM pages WHERE chapter_id = ? ORDER BY page_number",
                (chapter_id,),
            ).fetchall()
        ]


def test_scan_natural_sort_and_nested_paths(make_title, tmp_path):
    root = tmp_path / "Манга 東京"
    _make_chapter_dir(root, "Глава 10", ["1.png"])
    _make_chapter_dir(root, "Глава 2", ["10.png", "2.png", "1.png"])

    title_id = make_title()
    chapters_added, pages_added, skipped = _scan(title_id, root)

    assert (chapters_added, pages_added, skipped) == (2, 4, 0)
    chapters = _chapters(title_id)
    assert [c["chapter_number"] for c in chapters] == ["Глава 2", "Глава 10"]
    # Кириллица и японские символы в путях не ломаются.
    assert "東京" in chapters[0]["folder_path"]

    assert [p["page_number"] for p in _pages(chapters[0]["id"])] == [1, 2, 3]
    pages = _pages(chapters[0]["id"])
    assert [p["file_path"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in pages] == [
        "1.png",
        "2.png",
        "10.png",
    ]


def test_scan_skips_root_cover_when_chapter_subdirs_exist(make_title, tmp_path):
    root = tmp_path / "title"
    _touch(root / "cover.png")
    _make_chapter_dir(root, "Chapter 1", ["001.png", "002.png"])

    assert _has_image_subdirs(root) is True

    title_id = make_title()
    chapters_added, pages_added, _ = _scan(title_id, root)

    assert chapters_added == 1
    assert pages_added == 2
    assert [c["chapter_number"] for c in _chapters(title_id)] == ["Chapter 1"]


def test_scan_ignores_clean_and_translated_directories(make_title, tmp_path):
    root = tmp_path / "title"
    _make_chapter_dir(root, "Chapter 1", ["001.png"])
    for ignored in ("clean", "translated", "exports", "__pycache__"):
        _touch(root / ignored / "999.png")
        assert ignored in EXCLUDED_DIR_NAMES

    title_id = make_title()
    chapters_added, pages_added, _ = _scan(title_id, root)

    assert chapters_added == 1
    assert pages_added == 1
    assert [c["chapter_number"] for c in _chapters(title_id)] == ["Chapter 1"]


def test_scan_skip_existing_by_folder_path(make_title, tmp_path):
    root = tmp_path / "title"
    _make_chapter_dir(root, "Chapter 1", ["001.png"])
    _make_chapter_dir(root, "Chapter 2", ["001.png"])

    title_id = make_title()
    _scan(title_id, root)

    import os

    existing_folders = {
        os.path.normcase(os.path.abspath(c["folder_path"]))
        for c in _chapters(title_id)
    }
    added, pages, skipped = _scan(
        title_id, root, skip_existing=True, existing_folders=existing_folders
    )

    assert added == 0
    assert pages == 0
    assert skipped == 2  # обе главы уже в базе по folder_path


def test_scan_direct_root_images_create_single_chapter(make_title, tmp_path):
    root = tmp_path / "standalone"
    _touch(root / "page_10.png")
    _touch(root / "page_2.png")

    title_id = make_title()
    added, pages, _ = _scan(title_id, root, custom_chapter_name="Спецглава")

    assert (added, pages) == (1, 2)
    chapters = _chapters(title_id)
    assert chapters[0]["chapter_number"] == "Спецглава"
    assert [p["page_number"] for p in _pages(chapters[0]["id"])] == [1, 2]

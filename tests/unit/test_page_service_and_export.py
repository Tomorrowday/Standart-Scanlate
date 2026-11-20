# tests/unit/test_page_service_and_export.py
# Сохранение баблов, статусы страницы, клин пустой страницы, формат экспорта и бэкапы клина.

import io
import os

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from database import db_session, get_db
from routers.pages_handlers.common import (
    MAX_CLEAN_BACKUPS,
    _backup_clean_file_if_exists,
    _list_clean_backups,
    cleanup_other_pages_clean_backups,
)
from routers.pages_handlers.translated_export import save_translated_page
from schemas import TextBlockItem
from services.page_service_ops.active_settings import invalidate_global_settings_cache
from services.page_service_ops.clean_page import clean_page_bubbles_service
from services.page_service_ops.page_status import resolve_clean_status
from services.page_service_ops.save_blocks import save_page_blocks_service

pytestmark = pytest.mark.unit


def _block(block_id: str, **overrides) -> TextBlockItem:
    data = {
        "id": block_id,
        "x": 0.1,
        "y": 0.1,
        "width": 0.3,
        "height": 0.2,
        "rotation": 0.0,
        "jap_text": "",
        "rus_text": "",
        "speaker": "",
        "order_index": 0,
        "font_size": None,
        "font_family": "v_CCFaceFront",
        "is_bold": False,
        "is_italic": False,
        "is_uppercase": False,
        "has_stroke": False,
        "text_color": "black",
        "shape": "rect",
        "padding_mode": "safe",
        "min_hyphens": True,
        "status": "new",
    }
    data.update(overrides)
    return TextBlockItem(**data)


def _page_row(page_id: int) -> dict:
    with get_db() as conn:
        return dict(
            conn.execute(
                "SELECT status, clean_path FROM pages WHERE id = ?", (page_id,)
            ).fetchone()
        )


def test_save_blocks_clamps_coordinates_and_normalizes_rotation(make_page):
    page_id = make_page(page_number=1)

    status = save_page_blocks_service(
        page_id,
        [
            _block(
                "b1",
                x=-0.5,
                y=0.99,
                width=2.0,
                height=0.5,
                rotation=190.0,
                rus_text="Перевод",
                class_id=7,
                text_color="red",
                shape="weird",
                padding_mode="weird",
                min_hyphens=False,
            )
        ],
    )

    assert status == "translated"
    with get_db() as conn:
        row = dict(
            conn.execute(
                "SELECT * FROM text_blocks WHERE id = 'b1'"
            ).fetchone()
        )
    assert row["x"] == pytest.approx(0.0)
    assert row["y"] == pytest.approx(0.99)
    assert row["width"] == pytest.approx(1.0)
    assert row["height"] == pytest.approx(0.01)
    assert row["rotation"] == pytest.approx(-170.0)
    assert row["class_id"] == 7
    assert row["text_color"] == "black"
    assert row["shape"] == "rect"
    assert row["padding_mode"] == "safe"
    assert row["min_hyphens"] == 0

    # Отрицательный угол нормализуется в [-180, 180).
    save_page_blocks_service(page_id, [_block("b2", rotation=-200.0)])
    with get_db() as conn:
        rot = conn.execute("SELECT rotation FROM text_blocks WHERE id = 'b2'").fetchone()[0]
    assert rot == pytest.approx(160.0)


def test_save_blocks_recalculates_page_status(make_page, tmp_path):
    page_id = make_page(page_number=1)

    assert save_page_blocks_service(page_id, []) == "raw"
    assert save_page_blocks_service(page_id, [_block("b1")]) == "detected"

    # Наличие файла клина при отсутствии перевода даёт cleaned.
    clean_file = tmp_path / "clean" / "001.png"
    clean_file.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), "white").save(clean_file)
    with db_session() as cur:
        cur.execute(
            "UPDATE pages SET clean_path = ?, status = 'detected' WHERE id = ?",
            (str(clean_file), page_id),
        )
    assert save_page_blocks_service(page_id, [_block("b2")]) == "cleaned"

    assert save_page_blocks_service(page_id, [_block("b3", rus_text="Текст")]) == "translated"
    # Если clean_path отсутствует, пустой список не считается cleaned.
    with db_session() as cur:
        cur.execute("UPDATE pages SET clean_path = NULL WHERE id = ?", (page_id,))
    assert save_page_blocks_service(page_id, []) == "detected"

    # Статус done не понижается даже при сохранении пустого списка.
    with db_session() as cur:
        cur.execute("UPDATE pages SET status = 'done' WHERE id = ?", (page_id,))
    assert save_page_blocks_service(page_id, [_block("b4")]) == "done"


def test_resolve_clean_status():
    assert resolve_clean_status("done", has_rus=True) == "done"
    assert resolve_clean_status("translated") == "translated"
    assert resolve_clean_status("received", has_rus=True) == "translated"
    assert resolve_clean_status("raw") == "cleaned"
    assert resolve_clean_status(None) == "cleaned"


def test_clean_empty_page_is_skipped_and_keeps_existing_clean_path(make_page, tmp_path):
    page_id = make_page(page_number=1)
    clean_file = tmp_path / "manga" / "clean" / "001.png"
    clean_file.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 10), "white").save(clean_file)
    with db_session() as cur:
        cur.execute(
            "UPDATE pages SET clean_path = ?, status = 'cleaned' WHERE id = ?",
            (str(clean_file), page_id),
        )

    clean_path, status, stats = clean_page_bubbles_service(page_id)

    assert clean_path == str(clean_file)
    assert status == "cleaned"
    assert stats == {"white": 0, "inpaint": 0, "skipped": 1}


def _png_bytes(color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="PNG")
    return buf.getvalue()


def _set_export_format(value: str) -> None:
    with db_session() as cur:
        cur.execute("UPDATE global_settings SET export_format = ? WHERE id = 1", (value,))
    invalidate_global_settings_cache()


def test_translated_export_replaces_old_format_and_marks_done(make_page):
    page_id = make_page(page_number=1)
    with db_session() as cur:
        cur.execute("SELECT file_path FROM pages WHERE id = ?", (page_id,))
        orig_path = cur.fetchone()["file_path"]

    translated_dir = os.path.join(os.path.dirname(orig_path), "translated")

    _set_export_format("png")
    res = save_translated_page(
        page_id, UploadFile(file=io.BytesIO(_png_bytes()), filename="page.png")
    )
    png_path = res["saved_path"]
    assert png_path.endswith(".png")
    assert os.path.exists(png_path)

    _set_export_format("webp")
    res = save_translated_page(
        page_id, UploadFile(file=io.BytesIO(_png_bytes("gray")), filename="page.png")
    )
    webp_path = res["saved_path"]
    assert webp_path.endswith(".webp")
    assert os.path.exists(webp_path)
    assert not os.path.exists(png_path)  # старый формат удалён
    assert sorted(os.listdir(translated_dir)) == [os.path.basename(webp_path)]

    assert _page_row(page_id)["status"] == "done"


def test_clean_backups_keep_single_step_and_cleanup_other_pages(tmp_path):
    orig_path = str(tmp_path / "manga" / "001.png")
    clean_dir = tmp_path / "manga" / "clean"
    clean_dir.mkdir(parents=True)
    clean_path = clean_dir / "001.png"
    clean_path.write_bytes(b"first")

    _backup_clean_file_if_exists(orig_path, str(clean_path))
    assert len(_list_clean_backups(orig_path)) == MAX_CLEAN_BACKUPS == 1

    clean_path.write_bytes(b"second")
    _backup_clean_file_if_exists(orig_path, str(clean_path))
    backups = _list_clean_backups(orig_path)
    assert len(backups) == 1
    assert backups[0].endswith("_undo_backup_001.png")
    assert open(backups[0], "rb").read() == b"second"

    # Легаси-бэкап без индекса тоже учитывается и вытесняется.
    legacy = clean_dir / "001_undo_backup.png"
    legacy.write_bytes(b"legacy")
    assert len(_list_clean_backups(orig_path)) == 2
    _backup_clean_file_if_exists(orig_path, str(clean_path))
    assert not legacy.exists()
    assert len(_list_clean_backups(orig_path)) == 1

    # При открытии другой страницы бэкапы прочих страниц вычищаются.
    (clean_dir / "002_undo_backup_001.png").write_bytes(b"other")
    (clean_dir / "003_undo_backup_001.png").write_bytes(b"other")
    cleanup_other_pages_clean_backups(orig_path)
    remaining = sorted(p.name for p in clean_dir.glob("*_undo_backup*"))
    assert remaining == ["001_undo_backup_001.png"]

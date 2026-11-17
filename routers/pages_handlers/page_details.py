import os
from fastapi import HTTPException
from database import get_db
from routers.pages_handlers.common import cleanup_other_pages_clean_backups


def get_page_details(page_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.id, p.chapter_id, p.page_number, p.file_path, p.clean_path, p.status,
                   c.title_id, t.default_font_size
            FROM pages p
            JOIN chapters c ON c.id = p.chapter_id
            JOIN titles t ON t.id = c.title_id
            WHERE p.id = ?
            """,
            (page_id,)
        )
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    page_data = dict(row)
    if page_data.get("file_path"):
        cleanup_other_pages_clean_backups(str(page_data["file_path"]))

    if page_data.get("clean_path") and not os.path.exists(page_data["clean_path"]):
        page_data["clean_path"] = None

    return {"success": True, "page": page_data}

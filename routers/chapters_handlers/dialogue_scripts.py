import os
from urllib.parse import quote
from fastapi import HTTPException, UploadFile
from fastapi.responses import Response
import services.chapter_service as chapter_service
from logger import logger


def _build_attachment_header(filename: str) -> str:
    """Формирует Content-Disposition с ASCII-фоллбэком и UTF-8 именем (RFC 5987)."""
    # Убираем переводы строк и кавычки, чтобы нельзя было инжектировать заголовок.
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "").strip()
    if not safe_name:
        safe_name = "dialogues.json"
    ascii_fallback = safe_name.encode("ascii", "ignore").decode().strip() or "dialogues.json"
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(safe_name, safe='')}"
    )


def export_chapter_dialogue(chapter_id: int) -> Response:
    try:
        _, dialogues_json_str, _, dialogues_filename, _ = chapter_service.build_chapter_export_payloads(chapter_id)
        return Response(
            content=dialogues_json_str,
            media_type="application/json",
            headers={"Content-Disposition": _build_attachment_header(dialogues_filename)}
        )
    except Exception as e:
        logger.error(f"Ошибка экспорта диалогов главы {chapter_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def export_chapter_dialogue_to_folder_endpoint(chapter_id: int):
    try:
        return chapter_service.export_chapter_dialogue_to_folder(chapter_id)
    except Exception as e:
        logger.error(f"Ошибка экспорта диалогов в папку главы {chapter_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def import_chapter_dialogue(chapter_id: int, file: UploadFile):
    try:
        file_bytes = await file.read()
        res = chapter_service.import_chapter_dialogue_payload(chapter_id, file_bytes)
        return {
            "success": True,
            "message": f"Импортировано: обновлено {res['updated_count']} реплик из {res['total_records']} в файле.",
            **res
        }
    except Exception as e:
        logger.error(f"Ошибка импорта диалогов главы {chapter_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))


def pick_and_import_dialogue_endpoint(chapter_id: int):
    """
    Пытается автоматически найти и импортировать *_dialogues.json из папки главы.
    Если файл не найден, возвращает {"success": False, "auto_found": False, "cancelled": False},
    чтобы фронтенд открыл стандартное окно выбора файла без HTTP-ошибки 404.
    """
    target_file = None
    try:
        folder_path = chapter_service.get_chapter_folder_path(chapter_id)
        if not folder_path or not os.path.exists(folder_path):
            return {"success": False, "auto_found": False, "cancelled": False}

        target_file = chapter_service.find_latest_dialogue_json_in_folder(chapter_id)
        if not target_file or not os.path.exists(target_file):
            return {"success": False, "auto_found": False, "cancelled": False}

        with open(target_file, "rb") as f:
            file_bytes = f.read()

        res = chapter_service.import_chapter_dialogue_payload(chapter_id, file_bytes)
        return {
            "success": True,
            "auto_found": True,
            "cancelled": False,
            "file_path": target_file,
            "file_used": os.path.basename(target_file),
            "message": f"Успешно импортирован '{os.path.basename(target_file)}': обновлено {res['updated_count']} реплик.",
            **res
        }
    except Exception as e:
        logger.error(f"Ошибка автоматического импорта главы {chapter_id}: {e}")
        # Файл нашли, но он битый/не импортировался — это реальная ошибка 400,
        # иначе фронтенд молча откроет диалог выбора и пользователь не поймёт причину.
        if target_file and os.path.exists(target_file):
            raise HTTPException(
                status_code=400,
                detail=f"Файл '{os.path.basename(target_file)}' повреждён: {e}",
            )
        return {"success": False, "auto_found": False, "cancelled": False, "error": str(e)}


def import_dialogue_from_folder_endpoint(chapter_id: int):
    return pick_and_import_dialogue_endpoint(chapter_id)

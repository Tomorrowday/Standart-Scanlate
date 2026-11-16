# services/dictionary_ops/db_builder.py
# Скачивание архивов Yomitan и сборка data/jp_dict.sqlite.
# Подключение/схема/статус вынесены в jp_dict_db.py, импорт ZIP — в yomitan_importer.py;
# файл сохраняет прежний публичный API для остальных модулей проекта.

import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from config import JP_DICT_DB_PATH, DICT_SOURCES_DIR
from logger import logger
from services.dictionary_ops.jp_dict_db import (
    _build_lock,
    _build_progress,
    dict_db_connection,
    ensure_jp_dict_schema,
    get_dict_db_connection,
    get_dictionary_status,
)
from services.dictionary_ops.starter_data import (
    DICT_DOWNLOAD_URLS,
    STARTER_MANGA_ENTRIES,
)
from services.dictionary_ops.yomitan_importer import (
    _extract_structured_text,
    extract_plain_senses,
    import_yomitan_zip,
)

__all__ = [
    "DICT_DOWNLOAD_URLS",
    "STARTER_MANGA_ENTRIES",
    "get_dict_db_connection",
    "dict_db_connection",
    "ensure_jp_dict_schema",
    "extract_plain_senses",
    "import_yomitan_zip",
    "get_dictionary_status",
    "download_and_build_dictionaries",
]


def _download_dictionary_zip(url: str, zip_path: Path) -> None:
    """Скачивает ZIP-архив словаря во временный файл и атомарно подменяет целевой."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = zip_path.with_suffix(zip_path.suffix + ".part")

    logger.info(f"[Dictionary] Скачивание {url} -> {zip_path}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MangaTranslator/2.0 (Local Offline Dictionary Builder)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120.0) as resp, open(tmp_path, "wb") as out_f:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)

        if not zipfile.is_zipfile(tmp_path):
            raise ValueError("Скачанный файл не является ZIP-архивом (возможно, ошибка сети или редирект на HTML)")
        tmp_path.replace(zip_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def download_and_build_dictionaries(
    sources: Optional[List[str]] = None,
    force_download: bool = False,
) -> Dict[str, Any]:
    """
    Скачивает архивы Yomitan (JMdict_russian.zip, warodai-yomitan.zip) в data/dictionaries/
    и собирает индексированную базу data/jp_dict.sqlite.
    Если в папке data/dictionaries уже лежат локальные .zip архивы — использует их.
    """
    if not _build_lock.acquire(blocking=False):
        return {"success": False, "message": "Сборка словаря уже выполняется", "status": get_dictionary_status()}

    target_sources = sources or ["jmdict_ru", "warodai"]
    imported_stats: Dict[str, int] = {}

    try:
        _build_progress["is_building"] = True
        _build_progress["error"] = None
        _build_progress["stage"] = "starting"
        _build_progress["message"] = "Подготовка базы словаря..."

        ensure_jp_dict_schema(JP_DICT_DB_PATH)

        existing_counts = get_dictionary_status(JP_DICT_DB_PATH).get("sources", {})

        for src_key in target_sources:
            url = DICT_DOWNLOAD_URLS.get(src_key)
            if not url:
                logger.warning(f"[Dictionary] Неизвестный источник словаря: {src_key}")
                continue

            # Докачиваем только недостающий словарь: уже загруженный источник пропускаем
            if not force_download and existing_counts.get(src_key, 0) > 5000:
                logger.info(
                    f"[Dictionary] Источник '{src_key}' уже загружен "
                    f"({existing_counts[src_key]} статей), пропуск."
                )
                imported_stats[src_key] = int(existing_counts[src_key])
                continue

            zip_filename = "JMdict_russian.zip" if src_key == "jmdict_ru" else f"{src_key}-yomitan.zip"
            zip_path = DICT_SOURCES_DIR / zip_filename

            if force_download or not zip_path.exists() or zip_path.stat().st_size < 10_000 or not zipfile.is_zipfile(zip_path):
                _build_progress["stage"] = f"downloading_{src_key}"
                _build_progress["message"] = f"Скачивание словаря {src_key} ({zip_filename})..."
                _download_dictionary_zip(url, zip_path)

            _build_progress["stage"] = f"importing_{src_key}"
            _build_progress["message"] = f"Индексация {zip_filename} в SQLite..."
            base_freq = 10000 if src_key == "warodai" else 20000
            cnt = import_yomitan_zip(zip_path, source_label=src_key, base_freq=base_freq)
            imported_stats[src_key] = cnt

        _build_progress["stage"] = "done"
        _build_progress["message"] = "Словарь успешно собран и проиндексирован!"
        _build_progress["is_building"] = False
        return {
            "success": True,
            "imported": imported_stats,
            "status": get_dictionary_status(),
        }
    except Exception as e:
        logger.error(f"[Dictionary] Ошибка сборки словаря: {e}")
        _build_progress["stage"] = "error"
        _build_progress["error"] = str(e)
        _build_progress["message"] = f"Ошибка: {e}"
        _build_progress["is_building"] = False
        return {
            "success": False,
            "error": str(e),
            "status": get_dictionary_status(),
        }
    finally:
        _build_progress["is_building"] = False
        _build_lock.release()

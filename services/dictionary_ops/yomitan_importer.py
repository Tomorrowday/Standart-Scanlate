# services/dictionary_ops/yomitan_importer.py
# Парсинг structured-content Yomitan v3 и батч-импорт ZIP-архива в data/jp_dict.sqlite

import json
import zipfile
from pathlib import Path
from typing import Any, List

from config import JP_DICT_DB_PATH
from logger import logger
from services.dictionary_ops.jp_dict_db import (
    dict_db_connection,
    ensure_jp_dict_schema,
)


def _extract_structured_text(node: Any) -> str:
    """Рекурсивно извлекает читаемый текст из structured-content узлов Yomitan v3."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        parts = [_extract_structured_text(child) for child in node]
        return " ".join(p for p in parts if p).strip()
    if isinstance(node, dict):
        # Пропускаем чисто служебные блоки ссылок, если нужно, или вытаскиваем content
        content = node.get("content")
        if content is not None:
            return _extract_structured_text(content)
        text = node.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def extract_plain_senses(raw_glossary: list) -> List[str]:
    """Нормализует простые строки и structured-content объекты Yomitan v3 в чистые строки перевода."""
    result: List[str] = []
    for item in raw_glossary:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                result.append(cleaned)
        elif isinstance(item, dict):
            extracted = _extract_structured_text(item).strip()
            if extracted:
                result.append(extracted)
    return result


def import_yomitan_zip(
    zip_path: Path,
    source_label: str,
    base_freq: int = 50000,
    db_path: Path = JP_DICT_DB_PATH,
) -> int:
    """Импортирует ZIP-архив стандарта Yomitan v3 (term_bank_*.json) в data/jp_dict.sqlite."""
    zip_path = Path(zip_path)
    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Файл '{zip_path}' не найден или не является корректным ZIP-архивом")

    ensure_jp_dict_schema(db_path)

    inserted = 0
    batch: List[tuple] = []

    with dict_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA synchronous = OFF;")
        try:
            # Удаляем старые записи этого источника в рамках единой транзакции с новыми вставками,
            # чтобы параллельные читатели в режиме WAL не получали пустые ответы во время импорта
            cur.execute("DELETE FROM dict_entries WHERE source = ?", (source_label,))

            with zipfile.ZipFile(zip_path, "r") as zf:
                term_files = sorted(
                    f for f in zf.namelist()
                    if ("term_bank_" in f) and f.endswith(".json")
                )
                for tf in term_files:
                    try:
                        rows = json.loads(zf.read(tf).decode("utf-8"))
                    except Exception as e:
                        logger.warning(f"[Dictionary] Пропущен битый файл '{tf}' в '{zip_path.name}': {e}")
                        continue
                    if not isinstance(rows, list):
                        continue

                    for row in rows:
                        if not isinstance(row, list) or len(row) < 6:
                            continue
                        expr = str(row[0] or "").strip()
                        reading = str(row[1] or expr).strip()
                        def_tags = str(row[2] or "").strip()
                        rules = str(row[3] or "").strip()
                        try:
                            score = int(row[4] or 0)
                        except (TypeError, ValueError):
                            score = 0
                        raw_gloss = row[5] if isinstance(row[5], list) else []
                        seq = 0
                        if len(row) > 6 and row[6] is not None:
                            try:
                                seq = int(row[6])
                            except (TypeError, ValueError):
                                seq = 0
                        term_tags = str(row[7] or "").strip() if len(row) > 7 else ""

                        if not expr:
                            continue

                        senses = extract_plain_senses(raw_gloss)
                        if not senses:
                            continue

                        pos_combined = " ".join(filter(None, [def_tags, term_tags])).strip()
                        batch.append((
                            source_label,
                            seq,
                            expr,
                            reading,
                            rules,
                            pos_combined,
                            json.dumps(senses[:8], ensure_ascii=False),
                            base_freq,
                            score,
                        ))
                        if len(batch) >= 4000:
                            cur.executemany(
                                """
                                INSERT INTO dict_entries
                                (source, seq_id, kanji, reading, rules, pos_tags, senses_json, freq_rank, score)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                batch,
                            )
                            inserted += len(batch)
                            batch.clear()

            if batch:
                cur.executemany(
                    """
                    INSERT INTO dict_entries
                    (source, seq_id, kanji, reading, rules, pos_tags, senses_json, freq_rank, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                inserted += len(batch)

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.execute("PRAGMA synchronous = NORMAL;")

    logger.info(f"[Dictionary] Импортировано {inserted} статей из '{zip_path.name}' (source={source_label}).")
    return inserted

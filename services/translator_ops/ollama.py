"""
Перевод реплик манги через локальную Ollama.

Общий сервис для страницы и главы: единый выбор модели (embedding-модели
исключаются), единый промпт и единый парсер `[N] текст` из services.translator.
Большие главы переводятся чанками, чтобы не переполнять контекстное окно и
не упираться в таймаут.
"""

import json
import urllib.request
from typing import Any, Dict, List, Optional

from config import OLLAMA_BASE_URL
from logger import logger
from services.translator import _parse_numbered_blocks, sanitize_translation

CLASS_TYPE_LABELS = {
    0: "bubble",
    1: "thought",
    2: "text",
    3: "sfx",
}

# Модели, которые не умеют чат-генерацию и ломают перевод.
EMBED_MARKERS = ("embed", "bge", "nomic-embed", "e5-", "gte-", "rerank")

CHUNK_SIZE = 25
MIN_CHUNK_SIZE = 10
MIN_CHUNK_COVERAGE = 0.6
CHUNK_TIMEOUT_SEC = 120.0


def list_ollama_models(base_url: str = OLLAMA_BASE_URL) -> List[str]:
    """Возвращает имена моделей, загруженных в локальную Ollama."""
    req_tags = urllib.request.Request(f"{base_url}/api/tags", method="GET")
    with urllib.request.urlopen(req_tags, timeout=2.5) as resp:
        tags_data = json.loads(resp.read().decode("utf-8"))
    return [m.get("name", "") for m in tags_data.get("models", []) if m.get("name")]


def pick_chat_model(models: List[str]) -> str:
    """Выбирает чат-модель, полностью игнорируя embedding/rerank-модели."""
    chat_models = [
        m for m in models
        if not any(marker in m.lower() for marker in EMBED_MARKERS)
    ]
    if not chat_models:
        raise RuntimeError(
            "В локальной Ollama нет чат-моделей (найдены только embedding). "
            "Загрузите, например, qwen2.5:7b."
        )
    preferred = next((m for m in chat_models if "qwen" in m.lower()), None)
    if preferred:
        return preferred
    return next((m for m in chat_models if "llama" in m.lower()), chat_models[0])


def _build_prompt(
    items: List[Dict[str, Any]],
    title_description: str,
    glossary_rows: Optional[List[Dict[str, Any]]],
) -> str:
    lines = []
    for idx, it in enumerate(items):
        b_type = CLASS_TYPE_LABELS.get(int(it.get("class_id") or 0), "bubble")
        spk = f"[{it['speaker']}] " if it.get("speaker") else ""
        lines.append(f"[{idx + 1}] ({b_type}) {spk}{it['text']}")

    glossary_text = ""
    if glossary_rows:
        g_lines = [
            f"- {g.get('jap_word') or ''} -> {g.get('rus_word')} ({g.get('context') or ''})"
            for g in glossary_rows
        ]
        glossary_text = "\nГлоссарий:\n" + "\n".join(g_lines) + "\n"

    synopsis_text = f"\nСинопсис:\n{title_description}\n" if title_description else ""

    return (
        "Ты профессиональный литературный переводчик манги с японского на русский язык.\n"
        "Переведи реплики по порядку. В скобках указан тип блока: "
        "(bubble) — живая речь в бабле, (thought) — мысли/нарратив, (text) — надпись на фоне, (sfx) — звук.\n"
        f"{synopsis_text}{glossary_text}\n"
        "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать в ответе тип блока, имена спикеров или пояснения!\n"
        "Формат ответа СТРОГО:\n"
        "[1] Русский перевод первой реплики\n"
        "[2] Русский перевод второй реплики\n\n"
        "Оригинал:\n" + "\n".join(lines)
    )


def _request_chunk(
    items: List[Dict[str, Any]],
    model: str,
    title_description: str,
    glossary_rows: Optional[List[Dict[str, Any]]],
) -> Dict[int, str]:
    """Переводит один чанк и возвращает {локальный индекс: перевод}."""
    prompt = _build_prompt(items, title_description, glossary_rows)
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 8192},
    }).encode("utf-8")

    req_gen = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_gen, timeout=CHUNK_TIMEOUT_SEC) as resp:
        gen_data = json.loads(resp.read().decode("utf-8"))

    parsed = _parse_numbered_blocks(gen_data.get("response", ""))
    return {
        idx: sanitize_translation(text)
        for idx, text in parsed.items()
        if 0 <= idx < len(items)
    }


def _translate_range(
    items: List[Dict[str, Any]],
    model: str,
    title_description: str,
    glossary_rows: Optional[List[Dict[str, Any]]],
    result: Dict[str, str],
    start: int,
    end: int,
    chunk_no: int,
    chunks_total: int,
) -> None:
    chunk = items[start:end]
    if not chunk:
        return

    logger.info(f"[Ollama] чанк {chunk_no}/{chunks_total}: реплики {start + 1}-{end}")
    translated = _request_chunk(chunk, model, title_description, glossary_rows)
    coverage = len(translated) / len(chunk)

    # Модель не разобрала большую часть чанка — дробим его и повторяем.
    if coverage < MIN_CHUNK_COVERAGE and len(chunk) > MIN_CHUNK_SIZE:
        logger.warning(
            f"[Ollama] низкое покрытие {coverage:.0%} для чанка "
            f"{start + 1}-{end}, повтор меньшими частями"
        )
        mid = start + (len(chunk) + 1) // 2
        _translate_range(items, model, title_description, glossary_rows, result, start, mid, chunk_no, chunks_total)
        _translate_range(items, model, title_description, glossary_rows, result, mid, end, chunk_no, chunks_total)
        return

    for idx, text in translated.items():
        if text.strip():
            result[items[start + idx]["id"]] = text


def translate_via_ollama(
    dialogue_items: List[Dict[str, Any]],
    title_description: str = "",
    glossary_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    """Переводит список реплик через Ollama чанками. Ошибки пробрасываются."""
    if not dialogue_items:
        return {}

    models = list_ollama_models()
    if not models:
        raise RuntimeError("В локальной Ollama не найдено загруженных моделей.")

    model = pick_chat_model(models)
    total = len(dialogue_items)
    chunks_total = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    result: Dict[str, str] = {}
    chunk_no = 0
    for start in range(0, total, CHUNK_SIZE):
        chunk_no += 1
        end = min(start + CHUNK_SIZE, total)
        _translate_range(
            dialogue_items, model, title_description, glossary_rows,
            result, start, end, chunk_no, chunks_total,
        )

    logger.info(f"[Ollama] переведено {len(result)} из {total} реплик (модель {model})")
    return result

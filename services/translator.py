"""
Сервис перевода текста манги (Gemini API, санитизация и разбор реплик).
Зависимости: re, ml.models (ml), schemas.BatchTranslateItem, logger, services.prompts
"""

import re
from typing import List, Dict, Any, Optional
from ml.models import ml
from schemas import BatchTranslateItem
from logger import logger
from services.prompts import (
    build_single_translate_prompt,
    build_page_batch_prompt,
    build_chapter_batch_prompt,
)

CLASS_TYPE_LABELS = {
    0: "bubble",
    1: "thought",
    2: "text",
    3: "sfx",
}


def _parse_numbered_blocks(raw_text: str) -> Dict[int, str]:
    """
    Разбирает нумерованный ответ LLM вида `[N] текст`.
    Строки без маркера присоединяются к предыдущему блоку через `\\n`,
    чтобы не терять многострочные переводы одной реплики.
    """
    blocks: Dict[int, List[str]] = {}
    order: List[int] = []
    current_idx: Optional[int] = None

    for raw_line in raw_text.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue

        match = re.match(r"^\[(\d+)\]\s*(.*)$", line)
        if match:
            current_idx = int(match.group(1)) - 1
            if current_idx not in blocks:
                blocks[current_idx] = []
                order.append(current_idx)
            blocks[current_idx].append(match.group(2))
        elif current_idx is not None:
            blocks[current_idx].append(line)

    return {idx: "\n".join(blocks[idx]) for idx in order}


def _strip_wrapping_quotes(text: str) -> str:
    """
    Снимает внешние кавычки только в том случае, если они действительно обрамляют
    ВСЮ реплику целиком, а не принадлежат двум разным цитатам в начале и в конце.
    """
    if len(text) < 2:
        return text

    # 1. Парные угловые кавычки «...»
    if text.startswith("«") and text.endswith("»"):
        depth = 0
        closed_before_end = False
        for idx, ch in enumerate(text):
            if ch == "«":
                depth += 1
            elif ch == "»":
                depth -= 1
                if depth == 0 and idx < len(text) - 1:
                    closed_before_end = True
                    break
        if not closed_before_end and depth == 0:
            return text[1:-1].strip()

    # 2. Прямые двойные кавычки "..."
    if text.startswith('"') and text.endswith('"'):
        # Снимаем только если внутри строки больше нет других прямых кавычек
        if text[1:-1].count('"') == 0:
            return text[1:-1].strip()

    return text


def sanitize_translation(text: str) -> str:
    """
    Удаляет случайные артефакты от нейросети в начале реплики:
    - Префиксы типа блока: '(bubble)', '(thought)', '(text)', '(sfx)'
    - Префиксы спикеров: '[デンジ]:', '[Макима]:', '[Speaker 1]:', 'Дэндзи:'
    - Лишние обрамляющие кавычки вокруг всей фразы
    """
    clean = text.strip()

    # 0. Срезаем префикс типа бабла, если модель повторила его из промпта
    clean = re.sub(r"^\((?:bubble|thought|text|sfx)\)\s*:?\s*", "", clean, flags=re.IGNORECASE)

    # 1. Срезаем префиксы вида [Имя в любых символах]: или [Имя]:
    clean = re.sub(r"^\[[^\]]+\]\s*:?\s*", "", clean)

    # 2. Безопасно убираем обрамляющие кавычки, если LLM обернула всю фразу целиком
    clean = _strip_wrapping_quotes(clean)

    return clean.strip()


def translate_single_text(text: str, title_description: str = "") -> str:
    """Перевод одиночной реплики."""
    if not ml.gemini_model:
        raise RuntimeError("Gemini API не сконфигурирован")

    prompt = build_single_translate_prompt(text, title_description)
    logger.info(f"--- [Gemini Single] Запрос:\n{text}")
    response = ml.gemini_model.generate_content(prompt)
    result = sanitize_translation(response.text.strip())
    logger.info(f"--- [Gemini Single] Ответ:\n{result}")
    return result


def translate_batch_items(
    items: List[BatchTranslateItem],
    title_description: str = "",
    glossary_rows: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, str]:
    """Пакетный перевод реплик одной страницы."""
    if not ml.gemini_model:
        raise RuntimeError("Gemini API не сконфигурирован")
    if not items:
        return {}

    lines = []
    for i, item in enumerate(items):
        b_type = CLASS_TYPE_LABELS.get(int(item.class_id or 0), "bubble")
        speaker_prefix = f"[{item.speaker}]: " if item.speaker and item.speaker.strip() else ""
        lines.append(f"[{i + 1}] ({b_type}) {speaker_prefix}{item.text}")

    dialogue_text = "\n".join(lines)
    prompt = build_page_batch_prompt(dialogue_text, title_description, glossary_rows)

    logger.info(f"=== [Gemini Page Batch] Отправка {len(items)} реплик на перевод ===")
    response = ml.gemini_model.generate_content(prompt)
    raw_text = response.text.strip()
    logger.info(f"=== [Gemini Page Batch] Ответ нейросети:\n{raw_text}")

    result_map = {}
    for idx, translated in _parse_numbered_blocks(raw_text).items():
        if 0 <= idx < len(items):
            item_id = items[idx].id
            result_map[item_id] = sanitize_translation(translated)

    return result_map


def translate_chapter_dialogues(
    chapter_dialogue: List[Dict[str, Any]],
    glossary_rows: List[Dict[str, Any]],
    title_description: str = ""
) -> Dict[str, str]:
    """Перевод реплик всей главы манги."""
    if not ml.gemini_model:
        raise RuntimeError("Gemini API не сконфигурирован")
    if not chapter_dialogue:
        return {}

    lines = []
    for i, item in enumerate(chapter_dialogue):
        b_type = CLASS_TYPE_LABELS.get(int(item.get("class_id") or 0), "bubble")
        spk = f"[{item['speaker']}]: " if item.get("speaker") else ""
        lines.append(f"[{i + 1}] ({b_type}) (Стр. {item['page']}) {spk}{item['text']}")

    full_text = "\n".join(lines)
    prompt = build_chapter_batch_prompt(full_text, title_description, glossary_rows)

    logger.info(f"========== [Gemini Chapter Batch] ЗАПРОС ПЕРЕВОДА ГЛАВЫ ==========")
    logger.info(f"Фраз: {len(chapter_dialogue)}, глоссарий: {len(glossary_rows)}, синопсис: {bool(title_description)}")

    response = ml.gemini_model.generate_content(prompt)
    raw_text = response.text.strip()
    logger.info(f"========== [Gemini Chapter Batch] ОТВЕТ ==========\n{raw_text}")

    result_map = {}
    for idx, trans in _parse_numbered_blocks(raw_text).items():
        if 0 <= idx < len(chapter_dialogue):
            block_id = chapter_dialogue[idx]["id"]
            result_map[block_id] = sanitize_translation(trans)

    logger.info(f"Успешно сопоставлено: {len(result_map)} из {len(chapter_dialogue)}")
    return result_map

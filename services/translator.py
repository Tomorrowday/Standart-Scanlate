"""
Общие утилиты перевода манги: разбор нумерованного ответа LLM и санитизация
перевода. Используется сервисом Ollama (services.translator_ops.ollama) и
импортом/экспортом диалогов.

Зависимости: re
"""

import re
from typing import Dict, List, Optional


def _parse_numbered_blocks(raw_text: str) -> Dict[int, str]:
    """
    Разбирает нумерованный ответ LLM вида `[N] текст`.
    Строки без маркера присоединяются к предыдущему блоку через `\\n`,
    чтобы не терять многострочные переводы одной реплики.
    """
    # Reasoning-модели (qwen3, deepseek-r1, qwq) выводят черновики в <think>...
    # Теги часто содержат собственные маркеры [1], которые иначе склеились бы
    # с финальным ответом.
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw_text, flags=re.IGNORECASE)
    # Генерация могла оборваться внутри <think> без закрывающего тега.
    cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)

    blocks: Dict[int, List[str]] = {}
    order: List[int] = []
    current_idx: Optional[int] = None

    for raw_line in cleaned.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue

        # Поддерживаем markdown-разметку: **[1]** текст и [1]: текст.
        match = re.match(r"^(?:\*{1,2})?\[(\d+)\](?:\*{1,2})?\s*:?\s*(.*)$", line)
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

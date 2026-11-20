# tests/unit/test_translator_and_ollama.py
# Разбор ответов LLM, санитизация и чанкинг перевода через Ollama.

import json

import pytest

from services import translator
from services.translator_ops import ollama

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _json_response(data) -> _FakeResponse:
    return _FakeResponse(json.dumps(data, ensure_ascii=False).encode("utf-8"))


# --- _parse_numbered_blocks -------------------------------------------------------


def test_parse_numbered_blocks_basic_and_multiline():
    raw = "[1] Первая реплика\nпродолжение\n[2] Вторая"
    parsed = translator._parse_numbered_blocks(raw)
    assert parsed == {0: "Первая реплика\nпродолжение", 1: "Вторая"}


def test_parse_numbered_blocks_strips_think_blocks():
    raw = (
        "<think>черновик [1] не должен попасть</think>\n"
        "[1] Финальный ответ\n"
        "[2] Ещё реплика"
    )
    parsed = translator._parse_numbered_blocks(raw)
    assert parsed == {0: "Финальный ответ", 1: "Ещё реплика"}


def test_parse_numbered_blocks_strips_unclosed_think():
    raw = "[1] Готово\n<think>оборванные размышления [2] мусор"
    parsed = translator._parse_numbered_blocks(raw)
    assert parsed == {0: "Готово"}


def test_parse_numbered_blocks_supports_markdown_and_colon():
    raw = "**[1]** Жирный маркер\n[2]: С двоеточием\n```json\n[3] Игнор кода?"
    parsed = translator._parse_numbered_blocks(raw)
    assert parsed[0] == "Жирный маркер"
    assert parsed[1] == "С двоеточием"


def test_parse_numbered_blocks_keeps_unknown_prefix_as_text():
    raw = "Вступление без маркера\n[1] Реплика"
    parsed = translator._parse_numbered_blocks(raw)
    assert parsed == {0: "Реплика"}


# --- sanitize_translation / _strip_wrapping_quotes --------------------------------


def test_sanitize_strips_block_type_and_speaker_prefixes():
    assert translator.sanitize_translation("(bubble): Привет") == "Привет"
    assert translator.sanitize_translation("[Дэндзи]: Привет") == "Привет"
    assert translator.sanitize_translation("(thought) Мысли") == "Мысли"


def test_strip_wrapping_quotes_only_for_whole_phrase():
    assert translator._strip_wrapping_quotes("«Привет»") == "Привет"
    assert translator._strip_wrapping_quotes('"Привет"') == "Привет"
    # Две разные цитаты в одной реплике не должны терять кавычки.
    assert translator._strip_wrapping_quotes("«Раз» и «два»") == "«Раз» и «два»"
    assert translator._strip_wrapping_quotes('"Раз" и "два"') == '"Раз" и "два"'


def test_sanitize_does_not_strip_quote_of_whole_phrase_with_inner_quotes():
    assert translator.sanitize_translation("«Он сказал «да»»") == "Он сказал «да»"


# --- pick_chat_model --------------------------------------------------------------


def test_pick_chat_model_rejects_embedding_and_prefers_qwen():
    models = ["nomic-embed-text:latest", "bge-m3", "llama3.1:8b", "qwen2.5:7b"]
    assert ollama.pick_chat_model(models) == "qwen2.5:7b"


def test_pick_chat_model_falls_back_to_llama_then_first():
    assert ollama.pick_chat_model(["embed-x", "llama3:8b", "gemma:2b"]) == "llama3:8b"
    assert ollama.pick_chat_model(["mistral:7b", "gemma:2b"]) == "mistral:7b"


def test_pick_chat_model_raises_when_only_embeddings():
    with pytest.raises(RuntimeError, match="embedding"):
        ollama.pick_chat_model(["nomic-embed-text", "bge-m3", "rerank-x"])


# --- translate_via_ollama: чанки и повтор половинками -----------------------------


def _item(i: int) -> dict:
    return {"id": f"id-{i}", "text": f"реплика {i}", "class_id": 0, "speaker": ""}


def test_translate_via_ollama_chunks_long_chapter(monkeypatch):
    items = [_item(i) for i in range(26)]
    generate_prompts: list[str] = []

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/api/tags"):
            return _json_response({"models": [{"name": "qwen2.5:7b"}]})
        body = json.loads(req.data.decode("utf-8"))
        generate_prompts.append(body["prompt"])
        # Считаем, сколько реплик реально попало в этот чанк.
        original = body["prompt"].split("Оригинал:", 1)[1]
        count = sum(1 for line in original.splitlines() if line.strip().startswith("["))
        text = "\n".join(f"[{i}] Перевод {i}" for i in range(1, count + 1))
        return _json_response({"response": text})

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)

    result = ollama.translate_via_ollama(items)

    assert len(result) == 26
    assert result["id-0"] == "Перевод 1"
    # Во втором чанке нумерация начинается заново с локального индекса 1.
    assert result["id-25"] == "Перевод 1"
    # Первый чанк (25 реплик) и второй (1 реплика) — два запроса генерации.
    assert len(generate_prompts) == 2


def test_translate_via_ollama_retries_chunk_by_halves_on_low_coverage(monkeypatch):
    items = [_item(i) for i in range(12)]
    generate_calls = 0

    def fake_urlopen(req, timeout=None):
        nonlocal generate_calls
        if req.full_url.endswith("/api/tags"):
            return _json_response({"models": [{"name": "qwen2.5:7b"}]})
        generate_calls += 1
        if generate_calls == 1:
            # Модель разобрала только 1 из 12 реплик — покрытие ниже 60%.
            return _json_response({"response": "[1] Только первая"})
        text = "\n".join(f"[{i}] Реплика {i}" for i in range(1, 7))
        return _json_response({"response": text})

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)

    result = ollama.translate_via_ollama(items)

    assert len(result) == 12
    # 1 исходный чанк + 2 повторных половинки.
    assert generate_calls == 3


def test_translate_via_ollama_does_not_split_small_low_coverage_chunk(monkeypatch):
    items = [_item(i) for i in range(5)]
    generate_calls = 0

    def fake_urlopen(req, timeout=None):
        nonlocal generate_calls
        if req.full_url.endswith("/api/tags"):
            return _json_response({"models": [{"name": "qwen2.5:7b"}]})
        generate_calls += 1
        return _json_response({"response": "[1] Одна"})

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)

    result = ollama.translate_via_ollama(items)

    assert result == {"id-0": "Одна"}
    assert generate_calls == 1


def test_translate_via_ollama_empty_input_returns_empty_without_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("сеть не должна вызываться для пустого списка")

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fail)
    assert ollama.translate_via_ollama([]) == {}

"""Подсервисы перевода: локальная Ollama, общие промпты и разбор ответов."""

from services.translator_ops.ollama import (
    translate_via_ollama,
    pick_chat_model,
    list_ollama_models,
)

__all__ = ["translate_via_ollama", "pick_chat_model", "list_ollama_models"]

# services/dictionary.py
"""
Сервис локального японско-русского словаря и морфологического анализатора.
Реализует пакет services/dictionary_ops/.
Зависимости: sqlite3, models GiNZA/SudachiPy (опционально), database.get_db
"""

from typing import Dict, Any, List, Optional
from services.dictionary_ops import (
    MangaDictionaryEngine,
    dict_engine,
    download_and_build_dictionaries,
    ensure_jp_dict_schema,
    get_dictionary_status as _get_db_dictionary_status,
    is_dictionary_building as _is_dictionary_building,
    import_yomitan_zip,
)

__all__ = [
    "MangaDictionaryEngine",
    "dict_engine",
    "ensure_jp_dict_schema",
    "import_yomitan_zip",
    "get_dictionary_status",
    "is_dictionary_building",
    "download_and_build_dictionaries",
    "analyze_bubble_text",
    "invalidate_glossary_cache",
]


def analyze_bubble_text(
    jap_text: str,
    title_id: Optional[int] = None,
    nlp_mode: str = "auto",
) -> List[Dict[str, Any]]:
    """Токенизирует японскую фразу бабла, выделяет термины глоссария и статьи из Warodai/JMdict."""
    return dict_engine.analyze_bubble(jap_text, title_id=title_id, nlp_mode=nlp_mode)


def invalidate_glossary_cache(title_id: Optional[int] = None) -> None:
    """Сбрасывает кэш автомата Ахо-Корасик для указанного тайтла."""
    dict_engine.invalidate_glossary_cache(title_id)


def get_dictionary_status() -> Dict[str, Any]:
    """Возвращает статистику базы словаря data/jp_dict.sqlite и активный NLP-бэкенд."""
    status = _get_db_dictionary_status()
    status["nlp"] = dict_engine.get_nlp_info()
    return status


def is_dictionary_building() -> bool:
    """Лёгкая проверка «идёт сборка словаря» без DDL и COUNT(*) по всей базе."""
    return _is_dictionary_building()

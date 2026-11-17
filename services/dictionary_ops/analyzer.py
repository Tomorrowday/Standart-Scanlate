# services/dictionary_ops/analyzer.py
# Морфологический анализатор баблов (GiNZA bert-large / electra / SudachiPy) + Aho-Corasick Глоссарий + SQLite
# Класс-оркестратор делегирует работу атомарным миксинам:
# - glossary_matcher.py — глоссарий тайтла и автоматы Aho-Corasick
# - sql_lookup.py — каскадный SQL-поиск и декомпозиция составных слов
# - span_postprocess.py — отделение 化 перед して/する и склейка союзов
# - nlp_tokenizers.py / sudachi_tokenizer.py / ginza_tokenizer.py / regex_tokenizer.py — токенизация
# Все вызовы Rust SudachiPy и spaCy/GiNZA сериализуются через self._nlp_lock

import threading
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import JP_DICT_DB_PATH
from services.dictionary_ops.db_builder import ensure_jp_dict_schema
from services.dictionary_ops.deinflector import kata_to_hira
from services.dictionary_ops.ginza_tokenizer import GinzaTokenizerMixin
from services.dictionary_ops.glossary_matcher import (
    HAS_AHOCORASICK,
    GlossaryMatcherMixin,
)
from services.dictionary_ops.models import (
    DictSense,
    GlossaryHit,
    TokenSpanOut,
)
from services.dictionary_ops.nlp_tokenizers import NlpTokenizersMixin
from services.dictionary_ops.regex_tokenizer import RegexTokenizerMixin
from services.dictionary_ops.span_postprocess import SpanPostprocessMixin
from services.dictionary_ops.sql_lookup import SqlLookupMixin
from services.dictionary_ops.sudachi_tokenizer import SudachiTokenizerMixin


class MangaDictionaryEngine(
    GlossaryMatcherMixin,
    SqlLookupMixin,
    SpanPostprocessMixin,
    SudachiTokenizerMixin,
    GinzaTokenizerMixin,
    RegexTokenizerMixin,
    NlpTokenizersMixin,
):
    def __init__(self, dict_db_path: Path = JP_DICT_DB_PATH):
        self.dict_db_path = dict_db_path
        self._lock = threading.RLock()
        # Отдельный лок для сериализации вызовов Rust-ядра SudachiPy и пайплайна spaCy/GiNZA
        # (предотвращает RuntimeError: Already borrowed в многопоточном FastAPI)
        self._nlp_lock = threading.RLock()
        self._sudachi_tokenizer = None
        self._sudachi_split_mode = None
        self._sudachi_mode_a = None
        self._spacy_nlp_map: Dict[str, Any] = {}
        self._active_nlp_backend: str = "uninitialized"
        self._glossary_cache: Dict[int, List[GlossaryHit]] = {}
        self._glossary_automatons: Dict[int, Any] = {}

        ensure_jp_dict_schema(self.dict_db_path)

    def unload_models(self) -> None:
        """Полностью выгружает пайплайны spaCy/GiNZA и SudachiPy из RAM.

        Вызывается кнопкой «Очистить VRAM/RAM» в шапке редактора. После сброса
        анализатор лениво переинициализирует нужный бэкенд при следующем запросе.
        """
        with self._nlp_lock:
            self._spacy_nlp_map.clear()
            self._sudachi_tokenizer = None
            self._sudachi_split_mode = None
            self._sudachi_mode_a = None
            self._active_nlp_backend = "uninitialized"

    def get_nlp_info(self) -> Dict[str, Any]:
        if self._active_nlp_backend == "uninitialized":
            self._init_sudachi()
        return {
            "active_backend": self._active_nlp_backend,
            "has_ahocorasick": HAS_AHOCORASICK,
            "loaded_ginza_models": list(self._spacy_nlp_map.keys()),
        }

    def analyze_bubble(
        self,
        text: str,
        title_id: Optional[int] = None,
        nlp_mode: str = "auto",
    ) -> List[Dict[str, Any]]:
        """Полный разбор текста бабла с приоритетным выделением терминов глоссария тайтла."""
        if not text:
            return []

        glossary_intervals = self.find_glossary_intervals(text, title_id)
        final_tokens: List[TokenSpanOut] = []
        cursor = 0

        for start, end, g_hit in glossary_intervals:
            if start > cursor:
                final_tokens.extend(self._tokenize_segment(text[cursor:start], nlp_mode=nlp_mode))

            _, _, dict_senses = self.lookup_sql_cascade(
                surface=g_hit.jap_word,
                sudachi_lemma=g_hit.jap_word,
                sudachi_norm=g_hit.jap_word,
                reading_hira=kata_to_hira(g_hit.jap_word),
            )
            final_tokens.append(
                TokenSpanOut(
                    surface=text[start:end],
                    lemma=g_hit.jap_word,
                    reading=kata_to_hira(g_hit.jap_word) if g_hit.jap_word != kata_to_hira(g_hit.jap_word) else "",
                    pos_ru="Глоссарий тайтла",
                    glossary_match=g_hit,
                    dict_entries=dict_senses,
                )
            )
            cursor = end

        if cursor < len(text):
            final_tokens.extend(self._tokenize_segment(text[cursor:], nlp_mode=nlp_mode))

        return [t.to_dict() for t in final_tokens]


# Глобальный синглтон движка словаря
dict_engine = MangaDictionaryEngine()

__all__ = [
    "MangaDictionaryEngine",
    "dict_engine",
    "DictSense",
    "GlossaryHit",
    "TokenSpanOut",
]

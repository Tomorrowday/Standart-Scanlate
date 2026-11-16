# services/dictionary_ops/nlp_tokenizers.py
# Инициализация NLP-бэкендов (SudachiPy / GiNZA) и выбор токенизатора для сегмента

from typing import Optional, Any, Dict, List

from logger import logger
from services.dictionary_ops.models import TokenSpanOut


class NlpTokenizersMixin:
    """Миксин движка: ленивая инициализация SudachiPy/GiNZA под общим локом."""

    _nlp_lock: Any
    _sudachi_tokenizer: Any
    _sudachi_split_mode: Any
    _sudachi_mode_a: Any
    _spacy_nlp_map: Dict[str, Any]
    _active_nlp_backend: str

    def _init_sudachi(self) -> bool:
        with self._nlp_lock:
            if self._sudachi_tokenizer is not None:
                return True
            try:
                from sudachipy import dictionary, tokenizer  # type: ignore
                for dict_type in ("full", "core", "small"):
                    try:
                        sudachi_dict = dictionary.Dictionary(dict=dict_type)
                        self._sudachi_tokenizer = sudachi_dict.create()
                        self._sudachi_split_mode = tokenizer.Tokenizer.SplitMode.B
                        self._sudachi_mode_a = tokenizer.Tokenizer.SplitMode.A
                        if self._active_nlp_backend == "uninitialized":
                            self._active_nlp_backend = f"sudachipy ({dict_type})"
                        logger.info(f"[Dictionary NLP] SudachiPy инициализирован (dict={dict_type}).")
                        return True
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"[Dictionary NLP] SudachiPy недоступен: {e}")
            return False

    def _get_spacy_ginza(self, preferred: str = "auto") -> Optional[Any]:
        """
        Загружает GiNZA v5.3+ (ja_ginza_bert_large -> ja_ginza_electra -> ja_ginza)
        под потокобезопасной блокировкой.
        """
        if preferred == "sudachi":
            return None

        if preferred == "bert_large":
            candidates = ["ja_ginza_bert_large"]
        elif preferred == "electra":
            candidates = ["ja_ginza_electra"]
        else:
            candidates = ["ja_ginza_bert_large", "ja_ginza_electra", "ja_ginza"]

        with self._nlp_lock:
            for model_name in candidates:
                if model_name in self._spacy_nlp_map:
                    self._active_nlp_backend = model_name
                    return self._spacy_nlp_map[model_name]

                try:
                    import spacy  # type: ignore
                    try:
                        spacy.prefer_gpu()
                    except Exception:
                        pass
                    nlp = spacy.load(model_name)
                    self._spacy_nlp_map[model_name] = nlp
                    self._active_nlp_backend = model_name
                    logger.info(f"[Dictionary NLP] Загружена модель GiNZA: {model_name}")
                    return nlp
                except Exception as e:
                    logger.debug(f"[Dictionary NLP] Модель {model_name} не загружена: {e}")
                    continue

        return None

    def _tokenize_segment(self, segment: str, nlp_mode: str = "auto") -> List[TokenSpanOut]:
        if not segment:
            return []

        if nlp_mode in ("bert_large", "electra"):
            nlp = self._get_spacy_ginza(nlp_mode)
            if nlp is not None:
                return self._tokenize_with_spacy_ginza(nlp, segment)

        if nlp_mode == "auto" and self._spacy_nlp_map:
            # Если модель GiNZA уже загружена в память — используем её в режиме Auto
            first_loaded = next(iter(self._spacy_nlp_map.values()))
            return self._tokenize_with_spacy_ginza(first_loaded, segment)

        if self._init_sudachi():
            return self._tokenize_with_sudachi(segment)

        nlp = self._get_spacy_ginza("auto")
        if nlp is not None:
            return self._tokenize_with_spacy_ginza(nlp, segment)

        return self._tokenize_fallback_regex(segment)

# services/dictionary_ops/subword_decomposer.py
# Декомпозиция составных слов в стиле Rikaikun: продуктивные суффиксы и поиск подслов-префиксов

from typing import List, Dict, Any, Tuple

from services.dictionary_ops.constants import (
    PRODUCTIVE_SUFFIXES_RU,
    SUFFIX_EXTRA_LEMMAS,
)
from services.dictionary_ops.deinflector import (
    kata_to_hira,
    deinflect_candidates,
)
from services.dictionary_ops.models import DictSense


class SubwordDecomposerMixin:
    """Миксин движка: разбор составного слова на корень, суффикс и подслова."""

    _nlp_lock: Any
    _sudachi_tokenizer: Any
    _sudachi_mode_a: Any

    def _decompose_subwords_and_suffixes(self, surface: str, sudachi_lemma: str) -> Tuple[List[str], List[DictSense]]:
        """
        Если составное слово (например, 暴力的, 悪魔化, マキマさん, 人間性) не найдено целиком:
        1) Проверяет продуктивные суффиксы (-的, -化, -性, -感, -たち, -さん и др.), ищет корень
           и подтягивает реальные словарные статьи для суффиксальных глаголов (например, 化する / 化す).
        2) Ищет самое длинное совпадающее подслово-префикс (как Rikaikun: 暴力的 -> 暴力 -> 暴)
           и оставшийся компонент.
        """
        target = sudachi_lemma or surface
        extra_chain: List[str] = []
        combined_senses: List[DictSense] = []

        # 1. Проверяем известные продуктивные суффиксы (например, 暴力 + 的, 悪魔 + 化)
        for sfx, (sfx_reading, sfx_pos, sfx_meanings) in sorted(
            PRODUCTIVE_SUFFIXES_RU.items(), key=lambda x: -len(x[0])
        ):
            for word_variant in dict.fromkeys([surface, target]):
                if word_variant.endswith(sfx) and len(word_variant) > len(sfx):
                    stem = word_variant[:-len(sfx)]
                    stem_cands = deinflect_candidates(stem)
                    stem_hira = kata_to_hira(stem)
                    if stem_hira and stem_hira != stem:
                        stem_cands.append((stem_hira, [], []))

                    _, stem_reasons, stem_senses = self._query_exact_terms(stem_cands)
                    if stem_senses:
                        extra_chain = stem_reasons + [f"+ {sfx} ({sfx_pos})"]
                        combined_senses.extend(stem_senses[:3])

                        # Подтягиваем реальные словарные статьи для самого суффикса/глагола (например, 化する / 化す)
                        extra_lemmas = SUFFIX_EXTRA_LEMMAS.get(sfx, [])
                        if extra_lemmas:
                            sfx_cands = [(lem, [], []) for lem in extra_lemmas]
                            _, _, db_sfx_senses = self._query_exact_terms(sfx_cands)
                            combined_senses.extend(db_sfx_senses[:2])

                        combined_senses.append(
                            DictSense(
                                source="warodai",
                                kanji=f"-{sfx}",
                                reading=sfx_reading,
                                pos=sfx_pos,
                                meanings=sfx_meanings,
                            )
                        )
                        return extra_chain, combined_senses[:7]

        # 2. Если токен длинный (составное слово из 2+ корней, например через Sudachi SplitMode.A или префиксы Rikaikun)
        sub_parts: List[str] = []
        if self._init_sudachi():
            with self._nlp_lock:
                # Ссылки берём под локом: unload_models() мог обнулить атрибуты.
                tokenizer = self._sudachi_tokenizer
                mode_a = self._sudachi_mode_a
                a_morphs = list(tokenizer.tokenize(surface, mode_a)) if tokenizer is not None and mode_a is not None else []
            if len(a_morphs) > 1:
                for am in a_morphs:
                    part_form = am.dictionary_form() or am.surface()
                    if part_form and part_form != surface and part_form not in sub_parts:
                        sub_parts.append(part_form)

        # Также добавляем префиксы по убыванию длины (как Rikaikun: от N-1 до 1 символа)
        if len(surface) >= 2:
            for length in range(len(surface) - 1, 0, -1):
                prefix = surface[:length]
                if prefix not in sub_parts:
                    sub_parts.append(prefix)

        seen_kanji = set()
        for part in sub_parts[:6]:
            part_cands = deinflect_candidates(part)
            _, _, part_senses = self._query_exact_terms(part_cands)
            for ps in part_senses[:2]:
                key = (ps.source, ps.kanji, ps.reading)
                if key not in seen_kanji:
                    seen_kanji.add(key)
                    combined_senses.append(ps)
            if len(combined_senses) >= 5:
                break

        return extra_chain, combined_senses[:6]


__all__ = ["SubwordDecomposerMixin"]

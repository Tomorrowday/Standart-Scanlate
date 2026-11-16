# services/dictionary_ops/regex_tokenizer.py
# Умный регулярный фоллбэк-токенизатор, если SudachiPy/GiNZA ещё не установлены

import re
from typing import List

from services.dictionary_ops.constants import SURU_SURFACE_PREFIXES
from services.dictionary_ops.deinflector import (
    kata_to_hira,
    deinflect_candidates,
)
from services.dictionary_ops.models import TokenSpanOut


class RegexTokenizerMixin:
    """Миксин движка: резервный разбор по регулярным выражениям и словарю."""

    def _tokenize_fallback_regex(self, segment: str) -> List[TokenSpanOut]:
        """
        Умный фоллбэк-токенизатор (если SudachiPy/GiNZA ещё не установлены):
        - отделяет японские падежные/конечные частицы от кандзи;
        - проверяет суффикс кандзи + окуригану по словарю (чтобы в 悪魔化して отделить 悪魔 от 化して,
          как это делает Rikaikun).
        """
        raw_chunks = re.findall(r"[一-龥々〆ヵヶ]+[ぁ-ん]*|[ァ-ヴー]+|[ぁ-ん]+|[^\s]", segment)
        PARTICLES = {
            "の", "が", "は", "を", "に", "へ", "と", "で", "も", "か", "や",
            "よ", "ね", "わ", "ぞ", "ぜ", "な", "さ",
        }
        spans: List[TokenSpanOut] = []

        for ch in raw_chunks:
            if re.match(r"^[、。！？…・「」『』（）()!?,.\s]+$", ch):
                spans.append(
                    TokenSpanOut(
                        surface=ch,
                        lemma=ch,
                        reading="",
                        pos_ru="Пунктуация",
                        is_punct_or_particle=True,
                    )
                )
                continue

            m_kanji_hira = re.match(r"^([一-龥々〆ヵヶ]+)([ぁ-ん]+)$", ch)
            if m_kanji_hira:
                kanji_part, hira_tail = m_kanji_hira.group(1), m_kanji_hira.group(2)
                full_cands = deinflect_candidates(ch)
                full_lemma, full_chain, full_senses = self._query_exact_terms(full_cands)
                if full_senses:
                    spans.append(
                        TokenSpanOut(
                            surface=ch,
                            lemma=full_lemma or ch,
                            reading=full_senses[0].reading if full_senses else "",
                            pos_ru="Глагол / Прил." if full_chain else "Слово",
                            inflection_chain=full_chain,
                            dict_entries=full_senses,
                        )
                    )
                    continue

                # Проверяем, не образует ли хвост кандзи + хирагана отдельный глагол
                # (например, в 悪魔化して: 悪魔 + 化して -> 化する / 化す)
                split_found = False
                if len(kanji_part) >= 2:
                    for split_idx in range(1, len(kanji_part)):
                        left_kanji = kanji_part[:split_idx]
                        right_verb_surf = kanji_part[split_idx:] + hira_tail
                        rv_cands = deinflect_candidates(right_verb_surf)
                        if right_verb_surf.startswith("化") and hira_tail.startswith(SURU_SURFACE_PREFIXES):
                            rv_cands.insert(0, ("化する", ["деепричастие (-te)"], []))
                            rv_cands.insert(1, ("化す", ["деепричастие (-te)"], []))
                        rv_lemma, rv_chain, rv_senses = self._query_exact_terms(rv_cands)
                        if rv_senses and (rv_chain or hira_tail.startswith(SURU_SURFACE_PREFIXES)):
                            lk_lemma, lk_chain, lk_senses = self.lookup_sql_cascade(
                                surface=left_kanji,
                                sudachi_lemma=left_kanji,
                                sudachi_norm=left_kanji,
                            )
                            spans.append(
                                TokenSpanOut(
                                    surface=left_kanji,
                                    lemma=lk_lemma,
                                    reading=lk_senses[0].reading if lk_senses else "",
                                    pos_ru="Существительное",
                                    inflection_chain=lk_chain,
                                    dict_entries=lk_senses,
                                )
                            )
                            spans.append(
                                TokenSpanOut(
                                    surface=right_verb_surf,
                                    lemma=rv_lemma or right_verb_surf,
                                    reading=rv_senses[0].reading if rv_senses else "",
                                    pos_ru="Глагол",
                                    inflection_chain=rv_chain,
                                    dict_entries=rv_senses,
                                )
                            )
                            split_found = True
                            break

                if split_found:
                    continue

                k_lemma, k_chain, k_senses = self.lookup_sql_cascade(
                    surface=kanji_part,
                    sudachi_lemma=kanji_part,
                    sudachi_norm=kanji_part,
                )
                spans.append(
                    TokenSpanOut(
                        surface=kanji_part,
                        lemma=k_lemma,
                        reading=k_senses[0].reading if k_senses else "",
                        pos_ru="Существительное",
                        inflection_chain=k_chain,
                        dict_entries=k_senses,
                    )
                )
                spans.extend(self._tokenize_fallback_regex(hira_tail))
                continue

            if re.match(r"^[ぁ-ん]+$", ch) and ch in PARTICLES:
                spans.append(
                    TokenSpanOut(
                        surface=ch,
                        lemma=ch,
                        reading=ch,
                        pos_ru="Частица",
                        is_punct_or_particle=True,
                    )
                )
                continue

            reading_hira = kata_to_hira(ch) if re.match(r"^[ァ-ヴーぁ-ん]+$", ch) else ""
            resolved_lemma, chain, senses = self.lookup_sql_cascade(
                surface=ch,
                sudachi_lemma=ch,
                sudachi_norm=ch,
                reading_hira=reading_hira,
            )
            spans.append(
                TokenSpanOut(
                    surface=ch,
                    lemma=resolved_lemma,
                    reading=senses[0].reading if senses else reading_hira,
                    pos_ru="Слово",
                    inflection_chain=chain,
                    dict_entries=senses,
                )
            )

        return self._coalesce_compound_spans(spans)

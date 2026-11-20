# services/dictionary_ops/sudachi_tokenizer.py
# Токенизация сегмента через SudachiPy SplitMode.B со склейкой предикатов и вспомогательных глаголов

from typing import Any, List

from services.dictionary_ops.constants import (
    COLLOQUIAL_AUX_VERB_LEMMAS,
    SURU_SURFACE_PREFIXES,
)
from services.dictionary_ops.deinflector import (
    POS_MAP_RU,
    kata_to_hira,
)
from services.dictionary_ops.models import TokenSpanOut


class SudachiTokenizerMixin:
    """Миксин движка: разбор через SudachiPy."""

    _nlp_lock: Any
    _sudachi_tokenizer: Any
    _sudachi_split_mode: Any

    def _tokenize_with_sudachi(self, segment: str) -> List[TokenSpanOut]:
        # Ссылки на токенизатор и режим берём строго под локом: параллельный
        # unload_models() может обнулить их между проверкой и обращением.
        with self._nlp_lock:
            tokenizer = self._sudachi_tokenizer
            if tokenizer is None:
                return self._tokenize_fallback_regex(segment)
            split_mode = self._sudachi_split_mode
            morphemes = list(tokenizer.tokenize(segment, split_mode))

        spans: List[TokenSpanOut] = []
        i = 0
        n = len(morphemes)

        while i < n:
            m = morphemes[i]
            pos_tuple = m.part_of_speech()
            pos_major = pos_tuple[0] if len(pos_tuple) > 0 else ""
            pos_sub = pos_tuple[1] if len(pos_tuple) > 1 else ""
            pos_detail = pos_tuple[2] if len(pos_tuple) > 2 else ""

            surface = m.surface()
            base_lemma = m.dictionary_form() or surface
            norm_form = m.normalized_form() or base_lemma
            reading_kata = m.reading_form() or ""

            ner_label = None
            if pos_sub == "固有名詞":
                if pos_detail == "人名":
                    ner_label = "PERSON"
                elif pos_detail in ("地名", "国"):
                    ner_label = "LOC"
                else:
                    ner_label = "PROPN"

            # Если морфема — суффикс 化, а сразу за ней идёт глагол する (して, した и т.д.),
            # превращаем её в начало глагольного предиката 化する!
            is_ka_before_suru = (
                surface == "化"
                and i + 1 < n
                and (morphemes[i + 1].dictionary_form() in ("する", "為る") or morphemes[i + 1].surface().startswith(SURU_SURFACE_PREFIXES))
            )
            if is_ka_before_suru:
                pos_major = "動詞"
                base_lemma = "化する"
                norm_form = "化する"

            if pos_major in ("動詞", "形容詞"):
                j = i + 1
                while j < n:
                    next_m = morphemes[j]
                    next_pos_tuple = next_m.part_of_speech()
                    next_pos = next_pos_tuple[0] if len(next_pos_tuple) > 0 else ""
                    next_sub = next_pos_tuple[1] if len(next_pos_tuple) > 1 else ""
                    next_surf = next_m.surface()
                    next_dict = next_m.dictionary_form() or next_surf
                    next_norm = next_m.normalized_form() or next_dict

                    is_aux = next_pos == "助動詞"
                    is_conj_particle = next_pos == "助詞" and next_sub == "接続助詞" and next_surf in (
                        "て", "で", "ちゃ", "じゃ", "ば", "たら", "ても", "なきゃ", "なくちゃ"
                    )
                    is_colloquial_aux_verb = next_pos == "動詞" and (
                        next_dict in COLLOQUIAL_AUX_VERB_LEMMAS
                        or next_norm in COLLOQUIAL_AUX_VERB_LEMMAS
                        or next_sub == "非自立可能"
                        or (is_ka_before_suru and j == i + 1)
                    )
                    is_neg_adj = next_pos == "形容詞" and next_dict in ("ない", "ねえ")

                    if is_aux or is_conj_particle or is_colloquial_aux_verb or is_neg_adj:
                        surface += next_surf
                        reading_kata += next_m.reading_form() or ""
                        j += 1
                    else:
                        break
                i = j
            else:
                i += 1

            reading_hira = kata_to_hira(reading_kata)
            pos_label = POS_MAP_RU.get(pos_sub) or POS_MAP_RU.get(pos_major, pos_major or "Слово")
            is_trivial = pos_major in ("補助記号", "記号", "空白") or (pos_major == "助詞" and len(surface) <= 1)

            if pos_major in ("補助記号", "記号", "空白"):
                spans.append(
                    TokenSpanOut(
                        surface=surface,
                        lemma=surface,
                        reading="",
                        pos_ru="Пунктуация",
                        is_punct_or_particle=True,
                    )
                )
            else:
                resolved_lemma, chain, senses = self.lookup_sql_cascade(
                    surface=surface,
                    sudachi_lemma=base_lemma,
                    sudachi_norm=norm_form,
                    reading_hira=reading_hira,
                )
                spans.append(
                    TokenSpanOut(
                        surface=surface,
                        lemma=resolved_lemma,
                        reading=reading_hira,
                        pos_ru=pos_label,
                        inflection_chain=chain,
                        is_punct_or_particle=(is_trivial and len(senses) == 0),
                        ner_label=ner_label,
                        dict_entries=senses,
                    )
                )

        return self._coalesce_compound_spans(spans)

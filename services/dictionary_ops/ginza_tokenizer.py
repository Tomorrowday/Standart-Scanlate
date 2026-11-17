# services/dictionary_ops/ginza_tokenizer.py
# Токенизация сегмента через spaCy/GiNZA (bert-large / electra / ja_ginza)

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


class GinzaTokenizerMixin:
    """Миксин движка: разбор через spaCy-пайплайн GiNZA."""

    _nlp_lock: Any

    def _tokenize_with_spacy_ginza(self, nlp: Any, segment: str) -> List[TokenSpanOut]:
        # КРИТИЧЕСКИ ВАЖНО: сериализуем вызов nlp(segment), так как внутри spaCy JapaneseTokenizer
        # дергает Rust SudachiPy RefCell, который падает с RuntimeError: Already borrowed при параллельном вызове!
        with self._nlp_lock:
            doc = nlp(segment)

        spans: List[TokenSpanOut] = []
        i = 0
        n = len(doc)

        while i < n:
            tok = doc[i]
            tag_parts = (tok.tag_ or "").split("-")
            pos_major = tag_parts[0] if tag_parts else tok.pos_
            pos_sub = tag_parts[1] if len(tag_parts) > 1 else ""

            surface = tok.text
            base_lemma = tok.lemma_ or surface
            norm_form = tok.norm_ or base_lemma
            morph_reading = tok.morph.get("Reading")
            reading_kata = morph_reading[0] if morph_reading else ""
            ner_label = tok.ent_type_ or None

            is_ka_before_suru = (
                surface == "化"
                and i + 1 < n
                and (doc[i + 1].lemma_ in ("する", "為る") or doc[i + 1].text.startswith(SURU_SURFACE_PREFIXES))
            )
            if is_ka_before_suru:
                pos_major = "動詞"
                base_lemma = "化する"
                norm_form = "化する"

            if pos_major in ("動詞", "形容詞") or tok.pos_ in ("VERB", "ADJ"):
                j = i + 1
                while j < n:
                    next_tok = doc[j]
                    nt_parts = (next_tok.tag_ or "").split("-")
                    nt_major = nt_parts[0] if nt_parts else next_tok.pos_
                    nt_sub = nt_parts[1] if len(nt_parts) > 1 else ""
                    nt_surf = next_tok.text
                    nt_lemma = next_tok.lemma_ or nt_surf
                    nt_norm = next_tok.norm_ or nt_lemma

                    is_aux = nt_major == "助動詞" or next_tok.pos_ == "AUX"
                    is_conj_particle = (nt_major == "助詞" or next_tok.pos_ == "SCONJ" or next_tok.pos_ == "PART") and nt_surf in (
                        "て", "で", "ちゃ", "じゃ", "ば", "たら", "ても", "なきゃ", "なくちゃ"
                    )
                    is_colloquial_aux = (nt_major == "動詞" or next_tok.pos_ in ("VERB", "AUX")) and (
                        nt_lemma in COLLOQUIAL_AUX_VERB_LEMMAS
                        or nt_norm in COLLOQUIAL_AUX_VERB_LEMMAS
                        or nt_sub == "非自立可能"
                        or (is_ka_before_suru and j == i + 1)
                    )
                    is_neg_adj = (nt_major == "形容詞" or next_tok.pos_ == "ADJ") and nt_lemma in ("ない", "ねえ")

                    if is_aux or is_conj_particle or is_colloquial_aux or is_neg_adj:
                        surface += nt_surf
                        nr = next_tok.morph.get("Reading")
                        if nr:
                            reading_kata += nr[0]
                        j += 1
                    else:
                        break
                i = j
            else:
                i += 1

            reading_hira = kata_to_hira(reading_kata)
            pos_label = POS_MAP_RU.get(pos_sub) or POS_MAP_RU.get(pos_major, pos_major or "Слово")
            is_punct = pos_major in ("補助記号", "記号") or tok.pos_ == "PUNCT"

            if is_punct:
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
                        is_punct_or_particle=(pos_major == "助詞" and len(surface) <= 1 and len(senses) == 0),
                        ner_label=ner_label,
                        dict_entries=senses,
                    )
                )

        return self._coalesce_compound_spans(spans)

# services/dictionary_ops/span_postprocess.py
# Пост-обработка токенов: отделение глагольного суффикса 化 перед して/する
# и склейка составных союзов/разговорных выражений

from typing import List

from services.dictionary_ops.constants import (
    COMPOUND_EXPRESSIONS_SET,
    SURU_SURFACE_PREFIXES,
)
from services.dictionary_ops.deinflector import kata_to_hira
from services.dictionary_ops.models import TokenSpanOut


class SpanPostprocessMixin:
    """Миксин движка: правки границ токенов перед отдачей результата на фронтенд."""

    def _split_verbalized_ka_before_suru(self, raw_spans: List[TokenSpanOut]) -> List[TokenSpanOut]:
        """
        Исправляет классический случай манги вроде 『悪魔化して来てる』:
        Если анализатор склеил [Сущ + 化] (напр. 悪魔化) в один токен, а сразу за ним идёт
        глагольная связка с する (напр. して来てる / した / する), и при этом само слово 『悪魔化』
        не является отдельным словарным словом или термином глоссария —
        разделяет его на:
          1) 『悪魔』 (Существительное)
          2) 『化して来てる』 (Глагол: лемма 化する / 化す + 来る)
        В точности как это делает Rikaikun / Yomitan!
        """
        if len(raw_spans) < 2:
            return raw_spans

        out: List[TokenSpanOut] = []
        i = 0
        n = len(raw_spans)

        while i < n:
            cur = raw_spans[i]
            if (
                i + 1 < n
                and cur.glossary_match is None
                and len(cur.surface) >= 3
                and cur.surface.endswith("化")
                and raw_spans[i + 1].glossary_match is None
                and raw_spans[i + 1].surface.startswith(SURU_SURFACE_PREFIXES)
            ):
                # Проверяем, есть ли точное словарное вхождение для X化 целиком
                exact_cands = [(cur.surface, [], [])]
                _, _, exact_senses = self._query_exact_terms(exact_cands)

                if not exact_senses:
                    noun_surf = cur.surface[:-1]
                    verb_surf = "化" + raw_spans[i + 1].surface

                    noun_reading = cur.reading[:-1] if cur.reading.endswith("か") else ""
                    verb_reading = "か" + (raw_spans[i + 1].reading or kata_to_hira(raw_spans[i + 1].surface))

                    n_lemma, n_chain, n_senses = self.lookup_sql_cascade(
                        surface=noun_surf,
                        sudachi_lemma=noun_surf,
                        sudachi_norm=noun_surf,
                        reading_hira=noun_reading,
                    )
                    v_lemma, v_chain, v_senses = self.lookup_sql_cascade(
                        surface=verb_surf,
                        sudachi_lemma="化する",
                        sudachi_norm="化する",
                        reading_hira=verb_reading,
                    )

                    out.append(
                        TokenSpanOut(
                            surface=noun_surf,
                            lemma=n_lemma,
                            reading=n_senses[0].reading if n_senses else noun_reading,
                            pos_ru="Существительное",
                            inflection_chain=n_chain,
                            is_punct_or_particle=False,
                            ner_label=cur.ner_label,
                            dict_entries=n_senses,
                        )
                    )
                    out.append(
                        TokenSpanOut(
                            surface=verb_surf,
                            lemma=v_lemma,
                            reading=verb_reading,
                            pos_ru="Глагол (суру)",
                            inflection_chain=v_chain or raw_spans[i + 1].inflection_chain,
                            is_punct_or_particle=False,
                            dict_entries=v_senses,
                        )
                    )
                    i += 2
                    continue

            out.append(cur)
            i += 1

        return out

    def _coalesce_compound_spans(self, raw_spans: List[TokenSpanOut]) -> List[TokenSpanOut]:
        """
        1) Отделяет глагольный суффикс 化 от существительного, если следом идёт して/する (『悪魔』 + 『化して来てる』).
        2) Объединяет соседние короткие морфемы, если вместе они образуют составной союз
           или устойчивое выражение манги (например, で + も -> でも, だ + から -> だから,
           か + も + しれ + ない -> かもしれない).
        """
        raw_spans = self._split_verbalized_ka_before_suru(raw_spans)
        if len(raw_spans) <= 1:
            return raw_spans

        result: List[TokenSpanOut] = []
        i = 0
        n = len(raw_spans)

        while i < n:
            merged_done = False
            # Проверяем окно от 4 до 2 соседних токенов
            for window in (4, 3, 2):
                if i + window > n:
                    continue
                slice_spans = raw_spans[i:i + window]
                if any(s.glossary_match is not None for s in slice_spans):
                    continue

                combined_surf = "".join(s.surface for s in slice_spans)
                combined_hira = kata_to_hira(combined_surf)

                if combined_surf in COMPOUND_EXPRESSIONS_SET or combined_hira in COMPOUND_EXPRESSIONS_SET:
                    combined_reading = "".join(s.reading or kata_to_hira(s.surface) for s in slice_spans)
                    lemma, chain, senses = self.lookup_sql_cascade(
                        surface=combined_surf,
                        sudachi_lemma=combined_surf,
                        sudachi_norm=combined_hira,
                        reading_hira=combined_reading,
                    )
                    result.append(
                        TokenSpanOut(
                            surface=combined_surf,
                            lemma=lemma,
                            reading=combined_reading,
                            pos_ru="Союз / Выражение",
                            inflection_chain=chain,
                            is_punct_or_particle=False,
                            dict_entries=senses,
                        )
                    )
                    i += window
                    merged_done = True
                    break

            if not merged_done:
                result.append(raw_spans[i])
                i += 1

        return result

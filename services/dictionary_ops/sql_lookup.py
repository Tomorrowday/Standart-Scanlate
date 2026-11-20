# services/dictionary_ops/sql_lookup.py
# SQL-поиск статей по data/jp_dict.sqlite и декомпозиция составных слов в стиле Rikaikun

import json
from typing import Optional, List, Dict, Any, Tuple

from logger import logger
from services.dictionary_ops.constants import SURU_SURFACE_PREFIXES
from services.dictionary_ops.jp_dict_db import get_readonly_dict_connection
from services.dictionary_ops.deinflector import deinflect_candidates
from services.dictionary_ops.models import DictSense
from services.dictionary_ops.subword_decomposer import SubwordDecomposerMixin


class SqlLookupMixin(SubwordDecomposerMixin):
    """Миксин движка: каскадный поиск Warodai -> JMdict RU -> JMdict EN и разбор подслов."""

    dict_db_path: Any
    _nlp_lock: Any
    _sudachi_tokenizer: Any
    _sudachi_mode_a: Any

    def _query_exact_terms(self, candidates: List[Tuple[str, List[str], List[str]]]) -> Tuple[Optional[str], List[str], List[DictSense]]:
        query_terms = [c[0] for c in candidates if c[0]]
        if not query_terms:
            return None, [], []

        unique_terms = list(dict.fromkeys(query_terms))
        placeholders = ",".join("?" for _ in unique_terms)
        # Два раздельных index lookup: точное совпадение по kanji всегда выше
        # омонимов по reading и не вытесняется ими за LIMIT 16.
        sql = f"""
            SELECT source, kanji, reading, rules, pos_tags, senses_json, freq_rank, score
            FROM (
                SELECT 0 AS match_priority,
                       source, kanji, reading, rules, pos_tags, senses_json, freq_rank, score
                FROM dict_entries
                WHERE kanji IN ({placeholders})
                UNION ALL
                SELECT 1 AS match_priority,
                       source, kanji, reading, rules, pos_tags, senses_json, freq_rank, score
                FROM dict_entries
                WHERE reading IN ({placeholders})
            )
            ORDER BY
                match_priority ASC,
                CASE source
                    WHEN 'warodai' THEN 1
                    WHEN 'jmdict_ru' THEN 2
                    WHEN 'jmdict_en' THEN 3
                    ELSE 4
                END ASC,
                freq_rank ASC,
                score DESC
            -- Чуть больше прежнего лимита: UNION ALL может вернуть одну и ту же
            -- статью дважды (kanji и reading совпали), Python дедуплицирует.
            LIMIT 32
        """

        try:
            conn = get_readonly_dict_connection(self.dict_db_path)
            rows = conn.execute(sql, unique_terms + unique_terms).fetchall()
        except Exception as e:
            logger.debug(f"Ошибка SQL-поиска словаря: {e}")
            rows = []

        matched_senses: List[DictSense] = []
        resolved_lemma: Optional[str] = None
        resolved_chain: List[str] = []
        seen_source_kanji = set()

        candidate_groups: Dict[str, List[Tuple[str, List[str], List[str]]]] = {}
        for candidate in candidates:
            candidate_groups.setdefault(candidate[0], []).append(candidate)

        for r in rows:
            db_kanji = r["kanji"]
            db_reading = r["reading"]
            db_rules = set((r["rules"] or "").split())

            matched_candidate: Optional[Tuple[str, List[str], List[str]]] = None
            fallback_candidate: Optional[Tuple[str, List[str], List[str]]] = None

            for cand_word in (db_kanji, db_reading):
                for candidate in candidate_groups.get(cand_word, []):
                    _, reasons, req_rules = candidate
                    if reasons and fallback_candidate is None:
                        fallback_candidate = candidate
                    if req_rules and db_rules and not db_rules.intersection(req_rules):
                        continue
                    matched_candidate = candidate
                    break
                if matched_candidate is not None:
                    break

            if matched_candidate is None:
                matched_candidate = fallback_candidate
            if matched_candidate is None:
                continue

            _, reasons, _ = matched_candidate
            if not reasons and fallback_candidate is not None and fallback_candidate[0] == matched_candidate[0]:
                reasons = fallback_candidate[1]
            if reasons and not resolved_chain:
                resolved_chain = reasons
                resolved_lemma = db_kanji
            elif resolved_lemma is None:
                resolved_lemma = db_kanji

            dedup_key = (r["source"], db_kanji, db_reading, r["senses_json"])
            if dedup_key in seen_source_kanji:
                continue
            seen_source_kanji.add(dedup_key)

            try:
                meanings = json.loads(r["senses_json"])
            except Exception:
                meanings = [str(r["senses_json"])]

            matched_senses.append(
                DictSense(
                    source=r["source"],
                    kanji=db_kanji,
                    reading=db_reading,
                    pos=r["pos_tags"] or "",
                    meanings=meanings,
                )
            )

        return resolved_lemma, resolved_chain, matched_senses[:6]

    def lookup_sql_cascade(
        self,
        surface: str,
        sudachi_lemma: str = "",
        sudachi_norm: str = "",
        reading_hira: str = "",
    ) -> Tuple[str, List[str], List[DictSense]]:
        candidates = deinflect_candidates(surface)

        for extra_form in (sudachi_lemma, sudachi_norm):
            if extra_form:
                candidates.append((extra_form, [], []))
                for dec_cand in deinflect_candidates(extra_form):
                    if dec_cand not in candidates:
                        candidates.append(dec_cand)

        # Если глагольная форма начинается с 化 + форма する (например, 化して来てる или 化した),
        # добавляем кандидаты 化する и 化す, как это делает Rikaikun
        if surface.startswith("化") and len(surface) > 1:
            tail = surface[1:]
            if tail.startswith(SURU_SURFACE_PREFIXES):
                chain_hint = ["длительный вид (-teru)"] if ("てる" in tail or "ている" in tail) else ["деепричастие (-te)"]
                candidates.insert(0, ("化する", chain_hint, []))
                candidates.insert(1, ("化す", chain_hint, []))

        if reading_hira:
            candidates.append((reading_hira, [], []))

        resolved_lemma, resolved_chain, matched_senses = self._query_exact_terms(candidates)

        # Если это составной глагол с補助動詞 (например, して来てる / 化して来てる),
        # дополнительно подтягиваем статью для основного глагола в хвосте (来る / くる), если она не попала
        if ("来てる" in surface or "きてる" in surface or "来ている" in surface) and len(matched_senses) < 5:
            _, _, kuru_senses = self._query_exact_terms([("来る", [], []), ("くる", [], [])])
            for ks in kuru_senses[:2]:
                if all(ks.kanji != m.kanji or ks.source != m.source for m in matched_senses):
                    matched_senses.append(ks)

        # Если точного совпадения для составного слова нет (например, 暴力的 или 悪魔化) —
        # включаем декомпозицию корня и суффикса в стиле Rikaikun!
        if not matched_senses and len(surface) >= 2:
            decomp_chain, decomp_senses = self._decompose_subwords_and_suffixes(surface, sudachi_lemma)
            if decomp_senses:
                matched_senses = decomp_senses
                if decomp_chain and not resolved_chain:
                    resolved_chain = decomp_chain

        return resolved_lemma or sudachi_lemma or surface, resolved_chain, matched_senses

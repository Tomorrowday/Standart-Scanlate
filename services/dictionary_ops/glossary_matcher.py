# services/dictionary_ops/glossary_matcher.py
# Загрузка и кэширование глоссария тайтла из основной БД, автоматы Aho-Corasick
# и поиск непересекающихся вхождений терминов в тексте бабла

from typing import Optional, Any, List, Dict, Tuple

from database import get_db
from logger import logger
from services.dictionary_ops.models import GlossaryHit

try:
    import ahocorasick  # type: ignore
    HAS_AHOCORASICK = True
except ImportError:
    ahocorasick = None
    HAS_AHOCORASICK = False


class GlossaryMatcherMixin:
    """Миксин движка: работа с глоссарием тайтла (manga_db.sqlite) и кэшем автоматов."""

    _glossary_cache: Dict[int, List[GlossaryHit]]
    _glossary_automatons: Dict[int, Any]
    _lock: Any

    def invalidate_glossary_cache(self, title_id: Optional[int] = None) -> None:
        with self._lock:
            if title_id is None:
                self._glossary_cache.clear()
                self._glossary_automatons.clear()
            else:
                self._glossary_cache.pop(title_id, None)
                self._glossary_automatons.pop(title_id, None)

    def _load_title_glossary(self, title_id: int) -> List[GlossaryHit]:
        with self._lock:
            if title_id in self._glossary_cache:
                return self._glossary_cache[title_id]

        items: List[GlossaryHit] = []
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT id, jap_word, rus_word, context FROM glossary WHERE title_id = ? AND TRIM(jap_word) != ''",
                    (title_id,),
                ).fetchall()
                for r in rows:
                    jp = (r["jap_word"] or "").strip()
                    if jp:
                        items.append(
                            GlossaryHit(
                                id=int(r["id"]),
                                jap_word=jp,
                                rus_word=(r["rus_word"] or "").strip(),
                                context=(r["context"] or "").strip(),
                            )
                        )
        except Exception as e:
            logger.warning(f"Не удалось прочитать глоссарий для title_id={title_id}: {e}")

        with self._lock:
            self._glossary_cache[title_id] = items
            if HAS_AHOCORASICK and items:
                automaton = ahocorasick.Automaton()
                for hit in items:
                    automaton.add_word(hit.jap_word, (len(hit.jap_word), hit))
                automaton.make_automaton()
                self._glossary_automatons[title_id] = automaton

        return items

    def find_glossary_intervals(self, text: str, title_id: Optional[int]) -> List[Tuple[int, int, GlossaryHit]]:
        """Находит непересекающиеся вхождения терминов глоссария тайтла (приоритет длинным фразам)."""
        if not title_id or not text:
            return []

        items = self._load_title_glossary(title_id)
        if not items:
            return []

        raw_matches: List[Tuple[int, int, GlossaryHit]] = []
        automaton = self._glossary_automatons.get(title_id)

        if HAS_AHOCORASICK and automaton is not None:
            for end_idx, (term_len, hit) in automaton.iter(text):
                start_idx = end_idx - term_len + 1
                raw_matches.append((start_idx, end_idx + 1, hit))
        else:
            for hit in items:
                term = hit.jap_word
                start_pos = 0
                while True:
                    idx = text.find(term, start_pos)
                    if idx == -1:
                        break
                    raw_matches.append((idx, idx + len(term), hit))
                    start_pos = idx + 1

        if not raw_matches:
            return []

        raw_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        selected: List[Tuple[int, int, GlossaryHit]] = []
        last_end = -1
        for start, end, hit in raw_matches:
            if start >= last_end:
                selected.append((start, end, hit))
                last_end = end
        return selected

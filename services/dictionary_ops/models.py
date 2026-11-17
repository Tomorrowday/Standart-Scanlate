# services/dictionary_ops/models.py
# Датаклассы результатов морфологического разбора и статей локального словаря

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class DictSense:
    """Одна словарная статья (Warodai / JMdict) для токена бабла."""

    source: str
    kanji: str
    reading: str
    pos: str
    meanings: List[str]


@dataclass
class GlossaryHit:
    """Термин глоссария тайтла, найденный в тексте бабла."""

    id: int
    jap_word: str
    rus_word: str
    context: str


@dataclass
class TokenSpanOut:
    """Один токен (морфема или склеенный предикат) результата разбора."""

    surface: str
    lemma: str
    reading: str
    pos_ru: str
    inflection_chain: List[str] = field(default_factory=list)
    is_punct_or_particle: bool = False
    ner_label: Optional[str] = None  # "PERSON" | "LOC" | "ORG" от GiNZA bert-large/electra
    glossary_match: Optional[GlossaryHit] = None
    dict_entries: List[DictSense] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

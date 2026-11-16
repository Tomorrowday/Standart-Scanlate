# services/ocr_ops/text_normalizer.py
# Нормализация Юникода (NFKC) и японской пунктуации после распознавания OCR

import re
import unicodedata


def normalize_ocr_japanese_text(text: str) -> str:
    """Нормализация Юникода (NFKC) и японской пунктуации после распознавания."""
    if not text:
        return ""

    cleaned = unicodedata.normalize("NFKC", str(text))
    cleaned = re.sub(r'[\r\n\t]+', ' ', cleaned)

    # Убираем случайные пробелы между японскими символами
    cjk_char = r'[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]'
    cleaned = re.sub(f'({cjk_char})\\s+({cjk_char})', r'\1\2', cleaned)

    cleaned = re.sub(r'[:：]{2,}', '……', cleaned)
    cleaned = re.sub(r'(?<!\d)[:：](?!\d)', '…', cleaned)
    cleaned = re.sub(r'\.{2,}', '…', cleaned)
    cleaned = re.sub(r'[.…]{2,}', '…', cleaned)
    cleaned = re.sub(r'\s*…\s*', '…', cleaned)

    return cleaned.strip()


__all__ = ["normalize_ocr_japanese_text"]

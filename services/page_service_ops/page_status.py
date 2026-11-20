# services/page_service_ops/page_status.py
# Единый расчёт статуса страницы после клина/точечных правок

from typing import Optional


def resolve_clean_status(current: Optional[str], has_rus: bool = False) -> str:
    """
    Возвращает статус страницы после клина.

    - `done` не понижается;
    - `translated` (или наличие перевода в блоках) остаётся `translated`;
    - остальные случаи — `cleaned`.
    """
    current_status = str(current or "")
    if current_status == "done":
        return "done"
    if current_status == "translated" or has_rus:
        return "translated"
    return "cleaned"

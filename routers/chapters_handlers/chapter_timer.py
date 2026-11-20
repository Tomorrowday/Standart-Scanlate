import time
from typing import Optional, Tuple

from fastapi import HTTPException

from database import db_session

# Если от фронтенда не было heartbeat дольше этого времени, считаем, что
# вкладку/батник закрыли или пользователь ушёл, и закрываем сессию.
STALE_TIMER_TIMEOUT_SEC = 90


def _fetch_timer_row(cur, chapter_id: int):
    cur.execute(
        "SELECT work_seconds, timer_started_at, timer_last_seen_at FROM chapters WHERE id = ?",
        (chapter_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Глава не найдена")
    return row


def _reconcile_chapter_timer(
    cur, chapter_id: int, now: int
) -> Tuple[int, Optional[int], Optional[int]]:
    """Закрывает зависшую сессию таймера, засчитывая время только до последнего heartbeat.

    Возвращает кортеж (work_seconds, timer_started_at, timer_last_seen_at) после сверки.
    """
    row = _fetch_timer_row(cur, chapter_id)
    work_seconds = row["work_seconds"] or 0
    started_at = row["timer_started_at"]
    last_seen_at = row["timer_last_seen_at"]

    if started_at is not None:
        last_seen = last_seen_at if last_seen_at is not None else started_at
        if now - int(last_seen) > STALE_TIMER_TIMEOUT_SEC:
            delta = max(0, int(last_seen) - int(started_at))
            work_seconds += delta
            cur.execute(
                """
                UPDATE chapters
                SET work_seconds = ?, timer_started_at = NULL, timer_last_seen_at = NULL
                WHERE id = ?
                """,
                (work_seconds, chapter_id),
            )
            return work_seconds, None, None

    return work_seconds, started_at, last_seen_at


def _close_other_chapter_timers(cur, chapter_id: int) -> None:
    """Останавливает сессии таймера других глав, фиксируя время по их heartbeat."""
    cur.execute(
        """
        SELECT id, work_seconds, timer_started_at, timer_last_seen_at
        FROM chapters
        WHERE id != ? AND timer_started_at IS NOT NULL
        """,
        (chapter_id,),
    )
    for other in cur.fetchall():
        started_at = other["timer_started_at"]
        if started_at is None:
            continue
        now = int(time.time())
        last_seen = other["timer_last_seen_at"] or started_at
        # Живая сессия (heartbeat свежий) закрывается «до текущего момента»,
        # зависшая — только до последнего heartbeat, чтобы не начислить простой.
        if now - int(last_seen) <= STALE_TIMER_TIMEOUT_SEC:
            delta = max(0, now - int(started_at))
        else:
            delta = max(0, int(last_seen) - int(started_at))
        cur.execute(
            """
            UPDATE chapters
            SET work_seconds = ?, timer_started_at = NULL, timer_last_seen_at = NULL
            WHERE id = ?
            """,
            ((other["work_seconds"] or 0) + delta, other["id"]),
        )


def get_chapter_timer_status(chapter_id: int):
    now = int(time.time())
    with db_session() as cur:
        work_seconds, started_at, _ = _reconcile_chapter_timer(cur, chapter_id, now)

    is_running = started_at is not None
    current_session = max(0, now - int(started_at)) if is_running else 0
    total_seconds = work_seconds + current_session

    return {
        "success": True,
        "chapter_id": chapter_id,
        "is_running": is_running,
        "work_seconds": work_seconds,
        "current_session_seconds": current_session,
        "total_seconds": total_seconds,
    }


def start_chapter_timer(chapter_id: int):
    """Запускает таймер главы; повторный вызов работает как heartbeat активности."""
    now = int(time.time())
    with db_session() as cur:
        _, started_at, _ = _reconcile_chapter_timer(cur, chapter_id, now)
        _close_other_chapter_timers(cur, chapter_id)

        if started_at is None:
            cur.execute(
                "UPDATE chapters SET timer_started_at = ?, timer_last_seen_at = ? WHERE id = ?",
                (now, now, chapter_id),
            )
        else:
            cur.execute(
                "UPDATE chapters SET timer_last_seen_at = ? WHERE id = ?",
                (now, chapter_id),
            )

    return get_chapter_timer_status(chapter_id)


def stop_chapter_timer(chapter_id: int):
    now = int(time.time())
    with db_session() as cur:
        # Глава могла быть удалена (в т.ч. из другой вкладки) — остановка
        # таймера должна быть идемпотентной, без 404 в консоли браузера.
        cur.execute(
            "SELECT work_seconds, timer_started_at, timer_last_seen_at FROM chapters WHERE id = ?",
            (chapter_id,),
        )
        if not cur.fetchone():
            return {
                "success": True,
                "chapter_id": chapter_id,
                "is_running": False,
                "work_seconds": 0,
                "current_session_seconds": 0,
                "total_seconds": 0,
                "deleted": True,
            }

        work_seconds, started_at, _ = _reconcile_chapter_timer(cur, chapter_id, now)
        if started_at is not None:
            delta = max(0, now - int(started_at))
            cur.execute(
                """
                UPDATE chapters
                SET work_seconds = ?, timer_started_at = NULL, timer_last_seen_at = NULL
                WHERE id = ?
                """,
                (work_seconds + delta, chapter_id),
            )

    return get_chapter_timer_status(chapter_id)

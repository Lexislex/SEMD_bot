"""
Persistent notification jobs for NSI dictionary updates.

A detected update becomes a job (one per dictionary version) with a fixed message
text and one delivery row per chat. The job is written in the same transaction as
the NSI passport, so a failure between detection and sending can no longer lose the
notification: undelivered rows are retried later with a growing delay.

Delivery is at-least-once: if Telegram accepted a message but the process died
before the row was marked as sent, the message is sent again.

Stored in the FNSI database (``fnsi_data.sqlite``), tables ``notification_jobs``
and ``notification_deliveries``.
"""

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Union

from services.database_service import insert_nsi_passport

logger = logging.getLogger(__name__)

JOB_READY = "ready"  # message text is final, deliveries in progress
JOB_DONE = "done"  # every delivery is sent or failed

DELIVERY_PENDING = "pending"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"

# Delay before the next attempt after the N-th failure; the last value repeats
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=3),
    timedelta(hours=6),
)
# A notification older than this is not worth sending anymore
MAX_DELIVERY_AGE = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(value: datetime) -> str:
    """UTC timestamp that sorts and compares correctly as text."""
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Delivery:
    """One message of a job to one chat."""

    id: int
    job_id: int
    chat_id: int
    dictionary: str
    version: str
    payload: str
    attempts: int
    job_created_at: datetime


class NotificationStore:
    """SQLite-backed notification jobs and their per-chat deliveries."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        # detection runs in a thread pool; wait for a concurrent writer instead of failing
        return sqlite3.connect(self.db_path, timeout=30)

    def _ensure_tables(self) -> None:
        with closing(self._connect()) as con, con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS notification_jobs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "dictionary TEXT NOT NULL,"
                "version TEXT NOT NULL,"
                "payload TEXT NOT NULL,"
                "status TEXT NOT NULL,"
                "created_at TEXT NOT NULL,"
                "UNIQUE (dictionary, version)"
                ")"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS notification_deliveries ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "job_id INTEGER NOT NULL REFERENCES notification_jobs(id),"
                "chat_id INTEGER NOT NULL,"
                "status TEXT NOT NULL,"
                "message_id INTEGER,"
                "attempts INTEGER NOT NULL DEFAULT 0,"
                "next_attempt_at TEXT NOT NULL,"
                "last_error TEXT,"
                "updated_at TEXT NOT NULL,"
                "UNIQUE (job_id, chat_id)"
                ")"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS notification_deliveries_due "
                "ON notification_deliveries (status, next_attempt_at)"
            )

    # ---------------------------------------------------------------- jobs

    def create_job(
        self,
        fnsi_info: dict,
        payload: str,
        chat_ids: Iterable[int],
        now: Optional[datetime] = None,
    ) -> Optional[int]:
        """Store the passport, the job and its deliveries in one transaction.

        Args:
            fnsi_info: passport from FNSI (``id`` and ``version`` identify the job)
            payload: final HTML message text
            chat_ids: recipients, fixed at detection time

        Returns:
            Job id, or None if this dictionary version is already known.
        """
        now = now or utc_now()
        chats = list(dict.fromkeys(chat_ids))
        status = JOB_READY if chats else JOB_DONE
        with closing(self._connect()) as con:
            try:
                with con:
                    if not insert_nsi_passport(con, fnsi_info):
                        return None
                    job_id = con.execute(
                        "INSERT INTO notification_jobs "
                        "(dictionary, version, payload, status, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            fnsi_info["id"],
                            fnsi_info["version"],
                            payload,
                            status,
                            _ts(now),
                        ),
                    ).lastrowid
                    con.executemany(
                        "INSERT INTO notification_deliveries "
                        "(job_id, chat_id, status, next_attempt_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        [
                            (job_id, chat_id, DELIVERY_PENDING, _ts(now), _ts(now))
                            for chat_id in chats
                        ],
                    )
                    return job_id
            except sqlite3.IntegrityError:
                # another writer stored this version first
                return None

    # ---------------------------------------------------------- deliveries

    def due_deliveries(
        self, now: Optional[datetime] = None, limit: int = 100
    ) -> List[Delivery]:
        """Pending deliveries whose attempt time has come, oldest jobs first."""
        now = now or utc_now()
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT d.id, d.job_id, d.chat_id, j.dictionary, j.version, j.payload, "
                "d.attempts, j.created_at "
                "FROM notification_deliveries d "
                "JOIN notification_jobs j ON j.id = d.job_id "
                "WHERE d.status = ? AND d.next_attempt_at <= ? "
                "ORDER BY j.created_at, j.id, d.id LIMIT ?",
                (DELIVERY_PENDING, _ts(now), limit),
            ).fetchall()
        return [
            Delivery(*row[:7], job_created_at=datetime.fromisoformat(row[7]))
            for row in rows
        ]

    def mark_sent(
        self,
        delivery: Delivery,
        message_id: Optional[int],
        now: Optional[datetime] = None,
    ) -> None:
        self._finish(delivery, DELIVERY_SENT, message_id, None, now)

    def mark_failed(
        self, delivery: Delivery, error: str, now: Optional[datetime] = None
    ) -> None:
        """Give up on a delivery that cannot succeed (e.g. the bot was removed)."""
        self._finish(delivery, DELIVERY_FAILED, None, error, now)

    def mark_retry(
        self,
        delivery: Delivery,
        error: str,
        now: Optional[datetime] = None,
        retry_after: Optional[timedelta] = None,
    ) -> bool:
        """Schedule another attempt after a transient error.

        Args:
            retry_after: delay requested by Telegram (429), overrides the schedule

        Returns:
            False if the notification got too old and the delivery was given up.
        """
        now = now or utc_now()
        attempts = delivery.attempts + 1
        delay = retry_after or RETRY_DELAYS[min(attempts, len(RETRY_DELAYS)) - 1]
        next_attempt = now + delay
        if next_attempt - delivery.job_created_at > MAX_DELIVERY_AGE:
            self._finish(delivery, DELIVERY_FAILED, None, error, now, attempts)
            return False
        with closing(self._connect()) as con, con:
            con.execute(
                "UPDATE notification_deliveries "
                "SET attempts = ?, next_attempt_at = ?, last_error = ?, updated_at = ? "
                "WHERE id = ? AND status = ?",
                (
                    attempts,
                    _ts(next_attempt),
                    error[:500],
                    _ts(now),
                    delivery.id,
                    DELIVERY_PENDING,
                ),
            )
        return True

    def _finish(
        self,
        delivery: Delivery,
        status: str,
        message_id: Optional[int],
        error: Optional[str],
        now: Optional[datetime],
        attempts: Optional[int] = None,
    ) -> None:
        now = now or utc_now()
        with closing(self._connect()) as con, con:
            con.execute(
                "UPDATE notification_deliveries "
                "SET status = ?, message_id = ?, attempts = ?, last_error = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    status,
                    message_id,
                    attempts if attempts is not None else delivery.attempts + 1,
                    error[:500] if error else None,
                    _ts(now),
                    delivery.id,
                ),
            )
            con.execute(
                "UPDATE notification_jobs SET status = ? WHERE id = ? AND NOT EXISTS ("
                "SELECT 1 FROM notification_deliveries WHERE job_id = ? AND status = ?)",
                (JOB_DONE, delivery.job_id, delivery.job_id, DELIVERY_PENDING),
            )

"""
Persistent state of the schematron monitor (last seen commit per SEMD).

Stored in the FNSI database (``fnsi_data.sqlite``), table ``schematron_watch``.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

# Статусы последней проверки
STATUS_OK = "ok"
STATUS_NO_SCHEMATRON = "no_schematron"  # в ветке нет коммитов в schematron/
STATUS_REPO_NOT_FOUND = "repo_not_found"  # проект/ветка не найдены или скрыты от токена
STATUS_NOT_IN_1520 = "not_in_1520"
STATUS_NO_GIT_LINK = "no_git_link"
STATUS_ERROR = "error"


@dataclass
class WatchState:
    semd_oid: str
    git_link: Optional[str] = None
    last_sha: Optional[str] = None
    status: str = STATUS_OK
    last_checked: Optional[str] = None
    last_changed: Optional[str] = None


class SchematronStore:
    """SQLite-backed storage for WatchState rows."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_table(self) -> None:
        con = self._connect()
        try:
            with con:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS schematron_watch ("
                    "semd_oid TEXT PRIMARY KEY,"
                    "git_link TEXT,"
                    "last_sha TEXT,"
                    "status TEXT,"
                    "last_checked TEXT,"
                    "last_changed TEXT"
                    ")"
                )
        finally:
            con.close()

    def get(self, semd_oid: str) -> Optional[WatchState]:
        """Return stored state for a SEMD or None if it was never checked."""
        con = self._connect()
        try:
            row = con.execute(
                "SELECT semd_oid, git_link, last_sha, status, last_checked, last_changed "
                "FROM schematron_watch WHERE semd_oid = ?",
                (semd_oid,),
            ).fetchone()
        finally:
            con.close()
        return WatchState(*row) if row else None

    def get_all(self) -> Dict[str, WatchState]:
        """Return all stored states keyed by SEMD OID."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT semd_oid, git_link, last_sha, status, last_checked, last_changed "
                "FROM schematron_watch"
            ).fetchall()
        finally:
            con.close()
        return {row[0]: WatchState(*row) for row in rows}

    def save(self, state: WatchState) -> None:
        """Insert or replace state; last_checked is set to now."""
        state.last_checked = datetime.now().isoformat(timespec="seconds")
        con = self._connect()
        try:
            with con:
                con.execute(
                    "INSERT OR REPLACE INTO schematron_watch "
                    "(semd_oid, git_link, last_sha, status, last_checked, last_changed) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        state.semd_oid,
                        state.git_link,
                        state.last_sha,
                        state.status,
                        state.last_checked,
                        state.last_changed,
                    ),
                )
        finally:
            con.close()

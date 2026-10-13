"""
Persistent state of the schematron monitor (last seen commit per SEMD and kind).

Stored in the FNSI database (``fnsi_data.sqlite``): one table per artifact kind,
``schematron_watch`` for schematron and ``xsd_watch`` for XSD schemas. Separate
tables keep the old code (which keys rows by SEMD OID only) safe on rollback.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

KIND_SCHEMATRON = "schematron"
KIND_XSD = "xsd"
# Фиксированное соответствие вид -> таблица; имя таблицы берётся только отсюда
KIND_TABLES = {KIND_SCHEMATRON: "schematron_watch", KIND_XSD: "xsd_watch"}

# Статусы последней проверки
STATUS_OK = "ok"
STATUS_NO_SCHEMATRON = "no_schematron"  # в ветке нет коммитов в schematron/
STATUS_NO_FILES = "no_files"  # в ветке нет коммитов в папке вида (XSD)
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
    # Определяется таблицей, в строке не хранится
    kind: str = KIND_SCHEMATRON


class SchematronStore:
    """SQLite-backed storage for WatchState rows, one table per kind."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _table(kind: str) -> str:
        try:
            return KIND_TABLES[kind]
        except KeyError:
            raise ValueError(f"Неизвестный вид артефакта: {kind!r}") from None

    def _ensure_table(self) -> None:
        con = self._connect()
        try:
            with con:
                for table in KIND_TABLES.values():
                    con.execute(
                        f"CREATE TABLE IF NOT EXISTS {table} ("
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

    def get(self, semd_oid: str, kind: str = KIND_SCHEMATRON) -> Optional[WatchState]:
        """Return stored state for a SEMD and kind or None if it was never checked."""
        table = self._table(kind)
        con = self._connect()
        try:
            row = con.execute(
                "SELECT semd_oid, git_link, last_sha, status, last_checked, last_changed "
                f"FROM {table} WHERE semd_oid = ?",
                (semd_oid,),
            ).fetchone()
        finally:
            con.close()
        return WatchState(*row, kind=kind) if row else None

    def get_all(self, kind: str = KIND_SCHEMATRON) -> Dict[str, WatchState]:
        """Return all stored states of one kind keyed by SEMD OID."""
        table = self._table(kind)
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT semd_oid, git_link, last_sha, status, last_checked, last_changed "
                f"FROM {table}"
            ).fetchall()
        finally:
            con.close()
        return {row[0]: WatchState(*row, kind=kind) for row in rows}

    def save(self, state: WatchState) -> None:
        """Insert or replace state in its kind's table; last_checked is set to now."""
        table = self._table(state.kind)
        state.last_checked = datetime.now().isoformat(timespec="seconds")
        con = self._connect()
        try:
            with con:
                con.execute(
                    f"INSERT OR REPLACE INTO {table} "
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

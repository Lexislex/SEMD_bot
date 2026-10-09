"""
Database service - shared database operations for all plugins
"""

import logging
import sqlite3
from contextlib import closing
from datetime import datetime

from telebot import types

from config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()


def add_user(id, username, first_name, last_name):
    """Register a new user in the database"""
    with closing(sqlite3.connect(cfg.paths.user_db_path)) as conn:
        try:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS users ("
                    "id INTEGER PRIMARY KEY,"
                    "username TEXT,"
                    "first_name TEXT,"
                    "last_name TEXT,"
                    "reg_date TEXT"
                    ")"
                )
                conn.execute(
                    "INSERT INTO users"
                    "(id, username, first_name, last_name, reg_date)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (id, username, first_name, last_name, datetime.now().isoformat()),
                )
        except Exception as e:
            logger.warning(f"Warning: {e}")


def add_log(message):
    """Log user activity"""
    with closing(sqlite3.connect(cfg.paths.user_db_path)) as conn:
        try:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS users_activity"
                    " (id INTEGER, activity TEXT, date_time TEXT)"
                )
                known = (
                    conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
                    ).fetchone()
                    and conn.execute(
                        "SELECT id FROM users WHERE id = ?", (message.from_user.id,)
                    ).fetchone()
                )
            if not known:
                add_user(
                    message.from_user.id,
                    message.from_user.username,
                    message.from_user.first_name,
                    message.from_user.last_name,
                )

            if isinstance(message, types.CallbackQuery):
                log_text = message.data
            elif isinstance(message, types.Message):
                log_text = message.text
            else:
                log_text = "unknown type"
            with conn:
                conn.execute(
                    "INSERT INTO users_activity"
                    "(id, activity, date_time) VALUES (?, ?, ?)",
                    (message.from_user.id, log_text, datetime.now().isoformat()),
                )
        except Exception as e:
            logger.warning(f"Warning: {e}")


def get_activity(start_date="", stop_date=""):
    """Get user activity logs within date range"""
    with closing(sqlite3.connect(cfg.paths.user_db_path)) as conn:
        try:
            return conn.execute(
                "SELECT * FROM users_activity WHERE date_time BETWEEN ? AND ?",
                (start_date, stop_date),
            ).fetchall()
        except Exception as e:
            logger.warning(f"Warning: {e}")
            return None


NSI_PASSPORT_COLUMNS = (
    "ID, Name, ShortName, lastUpdate, version, releaseNotes, add_date"
)


def insert_nsi_passport(con: sqlite3.Connection, to_db: dict) -> bool:
    """
    Insert an NSI passport using the caller's connection, without committing.

    Lets a caller store the passport and related rows (e.g. a notification job)
    in one transaction.

    Args:
        con: open connection to the FNSI database
        to_db: NSI information (keys: id, fullName, shortName, lastUpdate,
            version, releaseNotes)

    Returns:
        bool: True if the passport was inserted, False if this version is already known
    """
    con.execute(f"CREATE TABLE IF NOT EXISTS nsi_passport ({NSI_PASSPORT_COLUMNS})")
    row = con.execute(
        "SELECT 1 FROM nsi_passport WHERE (ID = ? AND version = ?)",
        [to_db["id"], to_db["version"]],
    ).fetchone()
    if row is not None:
        return False
    con.execute(
        f"INSERT INTO nsi_passport ({NSI_PASSPORT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            to_db["id"],
            to_db["fullName"],
            to_db["shortName"],
            to_db["lastUpdate"],
            to_db["version"],
            to_db["releaseNotes"],
            datetime.now().isoformat(),
        ],
    )
    return True


def add_nsi_passport(to_db: dict) -> bool:
    """
    Add NSI (Reference Information System) passport to database.

    Checks if the NSI information exists in the database and adds it if not.

    Args:
        to_db (dict): Dictionary with NSI information to add
            (keys: id, fullName, shortName, lastUpdate, version, releaseNotes)

    Returns:
        bool: True if changes were made, False otherwise
    """
    with closing(sqlite3.connect(cfg.paths.fnsi_db_path)) as con:
        try:
            with con:
                return insert_nsi_passport(con, to_db)
        except Exception as e:
            logger.warning(f"Warning: {e}")
            return False

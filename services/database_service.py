"""
Database service - shared database operations for all plugins
"""
import sqlite3
from datetime import datetime
from telebot import types
from utils.database import create_table_nsi_passport
from config import get_config

import logging

logger = logging.getLogger(__name__)

cfg = get_config()


def add_user(id, username, first_name, last_name):
    """Register a new user in the database"""
    conn = sqlite3.connect(cfg.paths.user_db_path)
    cursor = conn.cursor()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS users ('
        'id INTEGER PRIMARY KEY,'
        'username TEXT,'
        'first_name TEXT,'
        'last_name TEXT,'
        'reg_date TEXT'
        ')'
    )
    try:
        cursor.execute(
            'INSERT INTO users'
            '(id, username, first_name, last_name, reg_date)'
            ' VALUES (?, ?, ?, ?, ?)',
            (id, username, first_name, last_name, datetime.now().isoformat())
        )
        conn.commit()
    except Exception as e:
        logger.warning(f'Warning: {e}')
        conn.commit()
        conn.close()


def add_log(message):
    """Log user activity"""
    conn = sqlite3.connect(cfg.paths.user_db_path)
    cursor = conn.cursor()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS users_activity'
        ' (id INTEGER, activity TEXT, date_time TEXT)'
    )
    cursor.execute('SELECT id FROM users WHERE id = ?', (message.from_user.id,))
    if cursor.fetchone() is None:
        add_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name
        )
    try:
        if isinstance(message, types.CallbackQuery):
            log_text = message.data
        elif isinstance(message, types.Message):
            log_text = message.text
        else:
            log_text = 'unknown type'
        cursor.execute(
            'INSERT INTO users_activity'
            '(id, activity, date_time) VALUES (?, ?, ?)',
            (message.from_user.id, log_text, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'Warning: {e}')
        conn.commit()
        conn.close()


def get_activity(start_date='', stop_date=''):
    """Get user activity logs within date range"""
    conn = sqlite3.connect(cfg.paths.user_db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT * FROM users_activity WHERE date_time BETWEEN ? AND ?',
            (start_date, stop_date)
        )
        res = cursor.fetchall()
        conn.close()
        return res
    except Exception as e:
        logger.warning(f'Warning: {e}')
        conn.close()
        return None


def add_nsi_passport(to_db: dict) -> bool:
    """
    Add NSI (Reference Information System) passport to database.

    Checks if the NSI information exists in the database and adds it if not.

    Args:
        to_db (dict): Dictionary with NSI information to add

    Returns:
        bool: True if changes were made, False otherwise
    """
    res = False
    con = sqlite3.connect(cfg.paths.fnsi_db_path)
    cur = con.cursor()

    # Check if table exists, create if it doesn't
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nsi_passport'")
    table_exists = cur.fetchone()
    if not table_exists:
        create_table_nsi_passport()

    # Check if record already exists
    cur.execute(
        "SELECT * FROM nsi_passport WHERE (ID = ? AND version = ?)",
        [to_db['id'], to_db['version']]
    )
    row = cur.fetchone()

    # If not found, add the record
    if row is None:
        try:
            now = datetime.now().isoformat()
            to_db['add_date'] = now
            cur.execute(
                "INSERT INTO nsi_passport"
                "(ID, Name, ShortName, lastUpdate, "
                "version, releaseNotes, add_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                list(to_db.values())
            )
            res = True
            con.commit()
            con.close()
        except Exception as e:
            logger.warning(f'Warning: {e}')
            con.close()
    return res

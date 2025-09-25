import sqlite3
from datetime import datetime
from telebot import types

# подключаем модули для dotenv
from config import get_config
cfg = get_config()

def add_user(id, usename, first_name, last_name):
    conn = sqlite3.connect(cfg.paths.user_db_path)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (\
                   id INTEGER PRIMARY KEY,\
                   username TEXT,\
                   first_name TEXT,\
                   last_name TEXT,\
                   reg_date TEXT\
                   )')
    try:
        cursor.execute(
            'INSERT INTO users'\
            '(id, username, first_name, last_name, reg_date)'\
            ' VALUES (?, ?, ?, ?, ?)',\
            (id, usename, first_name, last_name, datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        print('Warning:', e)
        conn.commit()
        conn.close()

def add_log(message):
    conn = sqlite3.connect(cfg.paths.user_db_path)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users_activity'\
                   ' (id INTEGER, activity TEXT, date_time TEXT)')
    cursor.execute('SELECT id FROM users WHERE id = ?',\
                   (message.from_user.id,))
    if cursor.fetchone() is None:
        add_user(message.from_user.id, message.from_user.username, \
                 message.from_user.first_name, message.from_user.last_name)
    try:
        if isinstance(message, types.CallbackQuery):
            log_text = message.data
        elif isinstance(message, types.Message):
            log_text = message.text
        else:
            log_text = 'unknown type'
        cursor.execute('INSERT INTO users_activity'\
                       '(id, activity, date_time) VALUES (?, ?, ?)',\
                       (message.from_user.id, log_text,\
                        datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print('Warning:', e)
        conn.commit()
        conn.close()

def get_activity(start_date = '', stop_date = ''):
    conn = sqlite3.connect(cfg.paths.user_db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM users_activity WHERE date_time BETWEEN ? AND ?',
                       (start_date, stop_date))
        res = cursor.fetchall()
        conn.close()
        return res
    except Exception as e:
        print('Warning:', e)
        conn.close()
        return None
    
def create_table_nsi_passport():
       # Подключение к базе данных
    con = sqlite3.connect(cfg.paths.fnsi_db_path)
    cur = con.cursor()
    try:
        cur.execute("CREATE TABLE nsi_passport"\
                    "(ID, Name, ShortName, lastUpdate, version, "\
                    "releaseNotes, add_date);")
        con.commit()
        # Закрываем подключение к базе
        con.close()
    except Exception as e:
        print('Warning:', e)
        # Закрываем подключение к базе
        con.close()


def add_nsi_passport(to_db: list) -> bool:
    """Эта функция проверяет наличие информации о справочнике ФНСИ в базе 
    и при отстутсвии добавляет в базу информацию о справочнике ФНСИ.
    если информация не добавлялась возвращается текст "Обновлений нет",
    если добавлялась, то возвращается текст "Обновления есть".

    Args:
        to_db (list): перечень информации для добавления в базу данных.
    Returns:
        bool:   True - внесены изменения в базу, False - нет.
    """
    res = False
    # Подключение к базе данных
    con = sqlite3.connect(cfg.paths.fnsi_db_path)
    cur = con.cursor()
    # Проверяем наличие таблицы в базе и если нет, то создаем.
    cur.execute("SELECT name FROM sqlite_master "\
                "WHERE type='table' AND name='nsi_passport'")
    table_exists = cur.fetchone()
    if not table_exists: create_table_nsi_passport()
    # Проверяем наличие информации в базе. 
    cur.execute("SELECT * FROM nsi_passport WHERE (ID = ? AND version = ?)",
                [to_db['id'], to_db['version']])
    row = cur.fetchone()
    # Если информация не найдена, то добавляем строку в базу.
    if row is None:
        try:
            # Получаем текущую дату и время
            now = datetime.now().isoformat()
            # Добавляем текущую дату и время к добавляемой информации
            to_db['add_date'] = now
            cur.execute("INSERT INTO nsi_passport"\
                        "(ID, Name, ShortName, lastUpdate, \
                        version, releaseNotes, add_date) \
                        VALUES (?, ?, ?, ?, ?, ?, ?);",
                        list(to_db.values()))
            res = True
            con.commit()
            # Закрываем подключение к базе
            con.close()
        except Exception as e:
            print('nen!')
            print('Warning:', e)
            # Закрываем подключение к базе
            con.close()
    return res

if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)
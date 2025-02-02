import sqlite3
from datetime import datetime
from telebot import types

def add_user(id, usename, first_name, last_name):
    conn = sqlite3.connect('env/data/user_data.sqlite')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (\
                   id INTEGER PRIMARY KEY,\
                   username TEXT,\
                   first_name TEXT,\
                   last_name TEXT,\
                   reg_date TEXT\
                   )')
    try:
        cursor.execute('INSERT INTO users (id, username, first_name, last_name, reg_date) VALUES (?, ?, ?, ?, ?)', \
                       (id, usename, first_name, last_name, datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        print('Warning:', e)
        conn.commit()
        conn.close()

def add_log(message):
    conn = sqlite3.connect('env/data/user_data.sqlite')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users_activity (\
                   id INTEGER PRIMARY KEY,\
                   activity TEXT,\
                   date_time TEXT\
                   )')
    cursor.execute('SELECT id FROM users WHERE id = ?', (message.from_user.id,))
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
        cursor.execute('INSERT INTO users_activity (id, activity, date_time) VALUES (?, ?, ?)', \
                       (message.from_user.id, log_text, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print('Warning:', e)
        conn.commit()
        conn.close()

def get_activity(start_date = '', stop_date = ''):
    conn = sqlite3.connect('env/data/user_data.sqlite')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM users_activity WHERE date_time between ? and ?', \
                       (start_date, stop_date))
        res = cursor.fetchall()
        conn.close()
        return res
    except Exception as e:
        print('Warning:', e)
        conn.close()
        return None


if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)
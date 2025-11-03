#!/usr/bin/env python3
"""Generate test data for statistics"""
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "env" / "data"
USER_DB_PATH = DATA_DIR / "user_data.sqlite"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

def generate_test_data():
    """Generate test activity data for the last 3 weeks"""
    conn = sqlite3.connect(USER_DB_PATH)
    cursor = conn.cursor()

    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            reg_date TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users_activity (
            id INTEGER,
            activity TEXT,
            date_time TEXT
        )
    ''')

    # Clear existing test data
    cursor.execute('DELETE FROM users_activity')
    cursor.execute('DELETE FROM users')

    # Test user IDs (not admin)
    test_users = [
        (123456789, 'user1', 'Иван', 'Петров'),
        (987654321, 'user2', 'Мария', 'Сидорова'),
        (456789123, 'user3', 'Петр', 'Иванов'),
    ]

    # Add users
    for user in test_users:
        cursor.execute(
            'INSERT INTO users (id, username, first_name, last_name, reg_date) VALUES (?, ?, ?, ?, ?)',
            (user[0], user[1], user[2], user[3], datetime.now().isoformat())
        )

    # Activities to log
    activities = [
        '/start',
        '/menu',
        'back_to_menu',
        'plugin_SEMDChecker',
        '123',  # SEMD search
        '456',  # SEMD search
        '789',  # SEMD search
        '/about',
        'plugin_Statistics',
        'plugin_AdminLogs',
        '/logs',
    ]

    # Generate random activity logs for the last 3 weeks
    now = datetime.now()
    three_weeks_ago = now - timedelta(days=21)

    for _ in range(150):  # Generate 150 log entries
        # Random user
        user_id = random.choice([u[0] for u in test_users])

        # Random activity
        activity = random.choice(activities)

        # Random datetime within last 3 weeks
        random_date = three_weeks_ago + timedelta(
            days=random.randint(0, 20),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )

        cursor.execute(
            'INSERT INTO users_activity (id, activity, date_time) VALUES (?, ?, ?)',
            (user_id, activity, random_date.isoformat())
        )

    conn.commit()
    conn.close()

    print(f"✅ Test data generated successfully!")
    print(f"📊 Generated 150 activity logs for 3 test users")
    print(f"📁 Database location: {USER_DB_PATH}")

if __name__ == '__main__':
    generate_test_data()

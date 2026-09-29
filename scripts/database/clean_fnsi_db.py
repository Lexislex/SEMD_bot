#!/usr/bin/env python3
"""
Скрипт для очистки базы данных FNSI для отладки и тестирования.

Использование:
    uv run python clean_fnsi_db.py              # Очистить все таблицы
    uv run python clean_fnsi_db.py --keep-schema   # Оставить схему, удалить только данные
    uv run python clean_fnsi_db.py --backup       # Создать резервную копию перед очисткой
    uv run python clean_fnsi_db.py --help         # Показать справку
"""

import sys
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
import argparse
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Путь к базе данных (scripts/database -> scripts -> SEMD_bot -> env/data)
DB_PATH = Path(__file__).parent.parent.parent / 'env' / 'data' / 'fnsi_data.sqlite'


def create_backup(db_path: Path) -> Path:
    """
    Создает резервную копию базы данных.

    Args:
        db_path: путь к базе данных

    Returns:
        Path: путь к созданной резервной копии
    """
    if not db_path.exists():
        logger.warning(f"База данных не найдена: {db_path}")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = db_path.parent / f'fnsi_data_backup_{timestamp}.sqlite'

    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"✅ Резервная копия создана: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"❌ Ошибка при создании резервной копии: {e}")
        return None


def get_table_info(db_path: Path) -> dict:
    """
    Получает информацию о таблицах в базе данных.

    Args:
        db_path: путь к базе данных

    Returns:
        dict: информация о таблицах и их размере
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Получаем список таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        table_info = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            row_count = cursor.fetchone()[0]
            table_info[table] = row_count

        conn.close()
        return table_info
    except Exception as e:
        logger.error(f"❌ Ошибка при получении информации о таблицах: {e}")
        return {}


def delete_database(db_path: Path) -> bool:
    """
    Полностью удаляет базу данных.

    Args:
        db_path: путь к базе данных

    Returns:
        bool: успешно ли удалена база данных
    """
    try:
        if db_path.exists():
            db_path.unlink()
            logger.info(f"✅ База данных удалена: {db_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении базы данных: {e}")
        return False


def clear_database_data(db_path: Path) -> bool:
    """
    Удаляет все данные из таблиц, сохраняя схему.

    Args:
        db_path: путь к базе данных

    Returns:
        bool: успешно ли очищена база данных
    """
    if not db_path.exists():
        logger.warning(f"База данных не найдена: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Получаем список таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            logger.info("ℹ️  В базе данных нет таблиц")
            return True

        # Отключаем проверку внешних ключей временно
        cursor.execute("PRAGMA foreign_keys = OFF;")

        # Очищаем каждую таблицу
        for table in tables:
            cursor.execute(f"DELETE FROM {table};")
            logger.info(f"   Очищена таблица: {table}")

        # Включаем проверку внешних ключей обратно
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Закрываем транзакцию перед VACUUM
        conn.commit()

        # Сжимаем базу данных (должно быть вне транзакции)
        cursor.execute("VACUUM;")

        conn.close()

        logger.info(f"✅ Все данные из базы удалены, схема сохранена")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке базы данных: {e}")
        return False


def print_db_info(db_path: Path):
    """
    Выводит информацию о базе данных.

    Args:
        db_path: путь к базе данных
    """
    if not db_path.exists():
        logger.warning(f"База данных не найдена: {db_path}")
        return

    table_info = get_table_info(db_path)

    if not table_info:
        logger.info("ℹ️  В базе данных нет таблиц")
        return

    db_size_mb = db_path.stat().st_size / (1024 * 1024)
    total_rows = sum(table_info.values())

    logger.info(f"📊 Информация о базе данных:")
    logger.info(f"   Путь: {db_path}")
    logger.info(f"   Размер: {db_size_mb:.2f} MB")
    logger.info(f"   Таблиц: {len(table_info)}")
    logger.info(f"   Всего записей: {total_rows}")
    logger.info(f"")
    logger.info(f"   Таблицы:")
    for table, count in sorted(table_info.items()):
        logger.info(f"      - {table}: {count} записей")


def main():
    parser = argparse.ArgumentParser(
        description='Скрипт для очистки базы данных FNSI для отладки и тестирования',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Примеры использования:
  uv run python clean_fnsi_db.py              # Полная очистка базы
  uv run python clean_fnsi_db.py --keep-schema   # Сохранить схему
  uv run python clean_fnsi_db.py --backup       # С резервной копией
  uv run python clean_fnsi_db.py --info         # Показать информацию
        '''
    )

    parser.add_argument(
        '--keep-schema',
        action='store_true',
        help='Удалить только данные, сохранить схему таблиц'
    )

    parser.add_argument(
        '--backup',
        action='store_true',
        help='Создать резервную копию перед очисткой'
    )

    parser.add_argument(
        '--info',
        action='store_true',
        help='Показать информацию о базе данных'
    )

    parser.add_argument(
        '--db-path',
        type=Path,
        default=DB_PATH,
        help=f'Путь к базе данных (по умолчанию: {DB_PATH})'
    )

    args = parser.parse_args()

    # Проверяем существование директории
    args.db_path.parent.mkdir(parents=True, exist_ok=True)

    # Только показать информацию
    if args.info:
        print_db_info(args.db_path)
        return 0

    # Подтверждение
    logger.warning("⚠️  Эта операция удалит данные из базы FNSI")
    print_db_info(args.db_path)

    response = input("\n❓ Вы уверены? (введите 'да' для подтверждения): ").strip().lower()
    if response != 'да':
        logger.info("❌ Операция отменена")
        return 1

    # Создаем резервную копию если требуется
    if args.backup:
        backup_path = create_backup(args.db_path)
        if not backup_path:
            logger.error("❌ Не удалось создать резервную копию")
            return 1

    # Выполняем очистку
    logger.info("🔄 Выполняется очистка базы данных...")

    if args.keep_schema:
        # Сохраняем схему, удаляем только данные
        success = clear_database_data(args.db_path)
    else:
        # Полная очистка - удаляем базу целиком
        success = delete_database(args.db_path)

    if success:
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ ОЧИСТКА УСПЕШНО ЗАВЕРШЕНА")
        logger.info("=" * 60)
        logger.info("")
        logger.info("💡 Что дальше:")
        logger.info("   1. При запуске бота будет создана новая структура БД")
        logger.info("   2. Начинайте тестирование с чистого листа")
        logger.info("   3. Если есть резервная копия - она в папке env/data/")
        logger.info("")
        return 0
    else:
        logger.error("")
        logger.error("=" * 60)
        logger.error("❌ ОШИБКА ПРИ ОЧИСТКЕ БАЗЫ")
        logger.error("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())

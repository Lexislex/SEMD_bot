#!/usr/bin/env python3
"""
Скрипт для полной очистки всех баз данных (FNSI и User).

Использование:
    poetry run python clean_all_db.py              # Очистить все базы
    poetry run python clean_all_db.py --backup      # С резервной копией
    poetry run python clean_all_db.py --info        # Показать информацию
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

# Пути к базам данных (scripts/database -> scripts -> SEMD_bot -> env/data)
DATA_DIR = Path(__file__).parent.parent.parent / 'env' / 'data'
FNSI_DB_PATH = DATA_DIR / 'fnsi_data.sqlite'
USER_DB_PATH = DATA_DIR / 'user_data.sqlite'


def get_db_info(db_path: Path) -> dict:
    """Получает информацию о базе данных."""
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        table_info = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            row_count = cursor.fetchone()[0]
            table_info[table] = row_count

        conn.close()

        db_size_mb = db_path.stat().st_size / (1024 * 1024)
        total_rows = sum(table_info.values())

        return {
            'path': db_path,
            'size_mb': db_size_mb,
            'tables': table_info,
            'total_rows': total_rows,
            'exists': True
        }
    except Exception as e:
        logger.error(f"Ошибка при получении информации о {db_path.name}: {e}")
        return None


def create_backup(db_path: Path) -> Path:
    """Создает резервную копию базы данных."""
    if not db_path.exists():
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = db_path.parent / f'{db_path.stem}_backup_{timestamp}.sqlite'

    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"   ✅ {db_path.name} → {backup_path.name}")
        return backup_path
    except Exception as e:
        logger.error(f"   ❌ Ошибка при создании резервной копии {db_path.name}: {e}")
        return None


def delete_database(db_path: Path) -> bool:
    """Удаляет базу данных."""
    try:
        if db_path.exists():
            db_path.unlink()
            logger.info(f"   ✅ Удалена: {db_path.name}")
            return True
        return False
    except Exception as e:
        logger.error(f"   ❌ Ошибка при удалении {db_path.name}: {e}")
        return False


def print_db_summary():
    """Выводит информацию о всех базах данных."""
    logger.info("📊 Информация о базах данных:")
    logger.info("")

    fnsi_info = get_db_info(FNSI_DB_PATH)
    user_info = get_db_info(USER_DB_PATH)

    for db_name, db_info in [("FNSI", fnsi_info), ("User", user_info)]:
        if db_info:
            logger.info(f"   📁 {db_name} ({db_info['path'].name})")
            logger.info(f"      Размер: {db_info['size_mb']:.2f} MB")
            logger.info(f"      Таблиц: {len(db_info['tables'])}")
            logger.info(f"      Записей: {db_info['total_rows']}")
            for table, count in sorted(db_info['tables'].items()):
                logger.info(f"         - {table}: {count}")
        else:
            logger.info(f"   📁 {db_name} — не существует")
        logger.info("")


def main():
    parser = argparse.ArgumentParser(
        description='Скрипт для очистки всех баз данных проекта',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Примеры использования:
  poetry run python clean_all_db.py              # Полная очистка
  poetry run python clean_all_db.py --backup      # С резервной копией
  poetry run python clean_all_db.py --info        # Показать информацию
        '''
    )

    parser.add_argument(
        '--backup',
        action='store_true',
        help='Создать резервные копии перед очисткой'
    )

    parser.add_argument(
        '--info',
        action='store_true',
        help='Показать информацию о базах данных'
    )

    args = parser.parse_args()

    # Создаем директорию если её нет
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Только показать информацию
    if args.info:
        print_db_summary()
        return 0

    # Показываем информацию перед очисткой
    logger.warning("⚠️  Эта операция удалит ВСЕ данные из баз данных")
    logger.info("")
    print_db_summary()

    response = input("❓ Вы уверены? (введите 'да' для подтверждения): ").strip().lower()
    if response != 'да':
        logger.info("❌ Операция отменена")
        return 1

    logger.info("")

    # Создаем резервные копии если требуется
    if args.backup:
        logger.info("🔄 Создание резервных копий...")
        create_backup(FNSI_DB_PATH)
        create_backup(USER_DB_PATH)
        logger.info("")

    # Удаляем базы данных
    logger.info("🔄 Удаление баз данных...")
    success_fnsi = delete_database(FNSI_DB_PATH)
    success_user = delete_database(USER_DB_PATH)
    logger.info("")

    if success_fnsi and success_user:
        logger.info("=" * 60)
        logger.info("✅ ВСЕ БАЗЫ УСПЕШНО ОЧИЩЕНЫ")
        logger.info("=" * 60)
        logger.info("")
        logger.info("💡 Информация:")
        logger.info("   • Базы будут пересозданы при запуске бота")
        logger.info("   • Резервные копии находятся в env/data/ (если были созданы)")
        logger.info("   • Проект полностью готов к новому циклу тестирования")
        logger.info("")
        return 0
    else:
        logger.error("")
        logger.error("=" * 60)
        logger.error("❌ ОШИБКА ПРИ ОЧИСТКЕ БАЗ")
        logger.error("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())

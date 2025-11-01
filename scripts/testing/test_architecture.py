#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой архитектуры
без запуска реального бота (без polling)
"""

import sys
import logging
from pathlib import Path

# Добавляем корневую директорию проекта в path
project_root = Path(__file__).parent.parent.parent  # scripts/testing -> scripts -> SEMD_bot
sys.path.insert(0, str(project_root))

# Загружаем конфиг и логирование
from config import get_config
from utils.logging_setup import setup_logging

cfg = get_config()
setup_logging(cfg)

logger = logging.getLogger(__name__)

def test_architecture():
    """Тестирует загрузку архитектуры и плагинов"""

    logger.info("=" * 60)
    logger.info("🧪 ТЕСТ АРХИТЕКТУРЫ SEMD Bot v2.0")
    logger.info("=" * 60)

    try:
        # 1. Тест создания ядра бота
        logger.info("\n1️⃣  Создание SEMDBotCore...")
        from core.bot import SEMDBotCore
        core = SEMDBotCore(cfg)
        logger.info("✅ SEMDBotCore создан успешно")
        logger.info(f"   - Bot token: {cfg.app.bot_token[:10]}***")
        logger.info(f"   - Environment: {cfg.app.env}")

        # 2. Тест загрузки NSI Updater плагина
        logger.info("\n2️⃣  Загрузка NSI Update Checker плагина...")
        success = core.load_plugin('plugins.nsi_update_checker')
        if success:
            logger.info("✅ NSI Update Checker загружен успешно")

            # Проверяем плагин
            plugin = core.plugin_manager.plugins.get('NSI_Update_Checker')
            if plugin:
                logger.info(f"   - Name: {plugin.get_name()}")
                logger.info(f"   - Version: {plugin.get_version()}")
                logger.info(f"   - Schedule config: {plugin.get_schedule_config()}")
        else:
            logger.error("❌ Ошибка загрузки NSI Update Checker")
            return False

        # 3. Тест получения задач планировщика
        logger.info("\n3️⃣  Получение задач для планировщика...")
        tasks = core.plugin_manager.get_scheduled_tasks()
        logger.info(f"✅ Получено {len(tasks)} задач(и)")
        for i, task in enumerate(tasks, 1):
            logger.info(f"   Задача {i}:")
            logger.info(f"      - Функция: {task['func'].__name__}")
            logger.info(f"      - Интервал: {task['interval']} {task['unit']}")

        # 4. Тест создания планировщика и добавления задач
        logger.info("\n4️⃣  Инициализация планировщика...")
        for task in tasks:
            core.scheduler.add_task(**task)
        logger.info(f"✅ {len(tasks)} задач(и) добавлено в планировщик")

        # 5. Проверка конфигурации
        logger.info("\n5️⃣  Проверка конфигурации...")
        logger.info(f"   - Accounts for mailing: {len(cfg.accounts.updates_mailing_list)} чатов")
        logger.info(f"   - FNSI API key: {cfg.apis.fnsi_api_key[:10]}***")
        logger.info(f"   - User DB path: {cfg.paths.user_db_path}")
        logger.info(f"   - FNSI DB path: {cfg.paths.fnsi_db_path}")

        logger.info("\n" + "=" * 60)
        logger.info("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        logger.info("=" * 60)
        logger.info("\n💡 Что дальше:")
        logger.info("   1. Запустить main.py для реального тестирования:")
        logger.info("      python3 main.py")
        logger.info("   2. Проверить логи в logs/")
        logger.info("   3. Убедиться что расписание работает")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"\n❌ ОШИБКА: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = test_architecture()
    sys.exit(0 if success else 1)

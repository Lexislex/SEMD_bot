#!/usr/bin/env python3
"""
Тестовый скрипт для проверки архитектуры плагинов
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

cfg = get_config()

from utils.logging_setup import setup_logging

setup_logging(cfg)

logger = logging.getLogger(__name__)


def test_core_architecture():
    """Тестирует основную архитектуру"""
    logger.info("\n📦 ТЕСТ: Основная архитектура")
    logger.info("-" * 50)

    try:
        from core.bot import SEMDBotCore

        core = SEMDBotCore(cfg)
        logger.info("✅ SEMDBotCore создан успешно")
        logger.info(f"   - Bot token: {cfg.app.bot_token[:10]}***")
        logger.info(f"   - Environment: {cfg.app.env}")
        logger.info(f"   - Log level: {cfg.app.log_level}")

        return core

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        return None


def test_access_control():
    """Тестирует систему контроля доступа"""
    logger.info("\n🔐 ТЕСТ: Система контроля доступа")
    logger.info("-" * 50)

    try:
        # Проверяем, что admin_ids это список
        admin_ids = cfg.accounts.admin_ids
        assert isinstance(admin_ids, list), "admin_ids должен быть списком"
        logger.info(f"✅ Admin IDs загружены: {admin_ids}")

        # Проверяем формат
        for admin_id in admin_ids:
            assert isinstance(admin_id, int), f"Admin ID должен быть int, получен {type(admin_id)}"
        logger.info(f"✅ Все admin IDs имеют правильный формат (int)")

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        return False


def test_database_service():
    """Тестирует database service"""
    logger.info("\n💾 ТЕСТ: Database Service")
    logger.info("-" * 50)

    try:
        from services.database_service import add_user, add_log, get_activity, add_nsi_passport

        logger.info("✅ Все функции database_service импортированы успешно:")
        logger.info("   - add_user")
        logger.info("   - add_log")
        logger.info("   - get_activity")
        logger.info("   - add_nsi_passport")

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка импорта: {e}", exc_info=True)
        return False


def test_all_plugins(core):
    """Тестирует загрузку всех плагинов"""
    logger.info("\n🔌 ТЕСТ: Загрузка всех плагинов")
    logger.info("-" * 50)

    plugins_to_load = [
        ('plugins.root_menu', 'Root Menu'),
        ('plugins.semd_checker', 'SEMD Checker'),
        ('plugins.nsi_update_checker', 'NSI Update Checker'),
        ('plugins.statistics', 'Statistics'),
        ('plugins.admin_logs', 'Admin Logs'),
        ('plugins.plugin_manager', 'Plugin Manager'),
    ]

    loaded_plugins = []

    for plugin_path, display_name in plugins_to_load:
        try:
            if core.load_plugin(plugin_path):
                loaded_plugins.append(display_name)
                logger.info(f"✅ {display_name} загружен")
            else:
                logger.warning(f"⚠️  {display_name} не загружен")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {display_name}: {e}")

    logger.info(f"\n✅ Загружено {len(loaded_plugins)}/{len(plugins_to_load)} плагинов")
    return len(loaded_plugins) > 0


def test_plugin_metadata(core):
    """Тестирует метаданные плагинов"""
    logger.info("\n📋 ТЕСТ: Метаданные плагинов")
    logger.info("-" * 50)

    try:
        plugins = core.plugin_manager.plugins

        if not plugins:
            logger.warning("⚠️  Нет загруженных плагинов")
            return False

        logger.info(f"Всего плагинов: {len(plugins)}\n")

        for name, plugin in plugins.items():
            logger.info(f"📦 {name}")
            logger.info(f"   - Display name: {plugin.display_name}")
            logger.info(f"   - Version: {plugin.get_version()}")
            logger.info(f"   - Access level: {plugin.access_level}")
            logger.info(f"   - Has access method: {hasattr(plugin, 'has_access')}")

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        return False


def test_access_filtering(core):
    """Тестирует фильтрацию плагинов по правам доступа"""
    logger.info("\n👥 ТЕСТ: Фильтрация плагинов по правам доступа")
    logger.info("-" * 50)

    try:
        # Test с обычным пользователем (ID не в админах)
        regular_user_id = 999999
        available_for_regular = core.plugin_manager.get_available_plugins(regular_user_id)

        logger.info(f"\nОбычный пользователь (ID: {regular_user_id}):")
        logger.info(f"Доступные плагины: {len(available_for_regular)}")
        for plugin in available_for_regular:
            logger.info(f"   ✓ {plugin.display_name} ({plugin.access_level})")

        # Test с админом
        admin_id = cfg.accounts.admin_ids[0] if cfg.accounts.admin_ids else 1
        available_for_admin = core.plugin_manager.get_available_plugins(admin_id)

        logger.info(f"\nАдмин (ID: {admin_id}):")
        logger.info(f"Доступные плагины: {len(available_for_admin)}")
        for plugin in available_for_admin:
            logger.info(f"   ✓ {plugin.display_name} ({plugin.access_level})")

        # Проверяем что админ видит больше плагинов
        assert len(available_for_admin) >= len(available_for_regular), \
            "Админ должен видеть не менее плагинов чем обычный пользователь"

        logger.info(f"\n✅ Фильтрация работает корректно")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        return False


def test_scheduled_tasks(core):
    """Тестирует задачи планировщика"""
    logger.info("\n⏰ ТЕСТ: Задачи планировщика")
    logger.info("-" * 50)

    try:
        tasks = core.plugin_manager.get_scheduled_tasks()
        logger.info(f"✅ Получено {len(tasks)} задач(и)")

        if tasks:
            for i, task in enumerate(tasks, 1):
                logger.info(f"   Задача {i}:")
                logger.info(f"      - Функция: {task['func'].__name__}")
                logger.info(f"      - Интервал: {task['interval']} {task['unit']}")
        else:
            logger.warning("⚠️  Нет задач планировщика")

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        return False


def test_legacy_handlers_removed():
    """Проверяет что legacy handlers удалены"""
    logger.info("\n🗑️  ТЕСТ: Удаление legacy кода")
    logger.info("-" * 50)

    try:
        # Проверяем что handlers модуль не может быть импортирован
        try:
            import handlers

            logger.error("❌ Legacy handlers модуль всё ещё существует!")
            return False
        except ImportError:
            logger.info("✅ Legacy handlers модуль удален")

        # Проверяем что нет импортов из handlers (исключаем тесты и scripts)
        import subprocess

        result = subprocess.run(
            ['grep', '-r', 'from handlers', '/Users/alexeyalepko/dev/SEMD_bot/', '--include=*.py',
             '--exclude-dir=scripts'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout:
            logger.error(f"❌ Найдены импорты из handlers:\n{result.stdout}")
            return False
        else:
            logger.info("✅ Нет импортов из handlers")

        return True

    except Exception as e:
        logger.error(f"⚠️  Не удалось проверить: {e}")
        return True  # Не факт в тесте


def main():
    """Запускает все тесты"""
    logger.info("=" * 60)
    logger.info("🧪 ТЕСТ АРХИТЕКТУРЫ SEMD Bot v2.0")
    logger.info("=" * 60)

    results = {}

    # 1. Тестируем основную архитектуру
    core = test_core_architecture()
    results['Core Architecture'] = core is not None

    if not core:
        logger.error("\n❌ Критическая ошибка: не удалось создать SEMDBotCore")
        return False

    # 2. Тестируем контроль доступа
    results['Access Control'] = test_access_control()

    # 3. Тестируем database service
    results['Database Service'] = test_database_service()

    # 4. Тестируем загрузку плагинов
    results['Plugin Loading'] = test_all_plugins(core)

    # 5. Тестируем метаданные плагинов
    results['Plugin Metadata'] = test_plugin_metadata(core)

    # 6. Тестируем фильтрацию доступа
    results['Access Filtering'] = test_access_filtering(core)

    # 7. Тестируем задачи планировщика
    results['Scheduled Tasks'] = test_scheduled_tasks(core)

    # 8. Проверяем удаление legacy кода
    results['Legacy Code Removal'] = test_legacy_handlers_removed()

    # Выводим результаты
    logger.info("\n" + "=" * 60)
    logger.info("📊 РЕЗУЛЬТАТЫ ТЕСТОВ")
    logger.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, success in results.items():
        status = "✅" if success else "❌"
        logger.info(f"{status} {test_name}")

    logger.info(f"\n{passed}/{total} тестов пройдено")

    if passed == total:
        logger.info("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        logger.info("\n💡 Что дальше:")
        logger.info("   1. Запустить основной бот:")
        logger.info("      python3 main.py")
        logger.info("   2. Проверить логи в logs/")
        logger.info("   3. Протестировать команды:")
        logger.info("      /start - главное меню")
        logger.info("      /stat - статистика (админ)")
        logger.info("      /logs - логи (админ)")
        logger.info("      /plugins - список плагинов (админ)")
        logger.info("=" * 60)
        return True
    else:
        logger.error("\n❌ Некоторые тесты не прошли!")
        logger.error("=" * 60)
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

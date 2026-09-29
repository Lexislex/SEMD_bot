# Загружаем переменные окружения
from config import get_config

cfg = get_config()

# Настройка логирования
from utils.logging_setup import setup_logging

setup_logging(cfg)

import logging

logger = logging.getLogger(__name__)

# Импортируем основной класс архитектуры
from core.bot import SEMDBotCore

# Создаём ядро бота с поддержкой плагинов
core = SEMDBotCore(cfg)


if __name__ == "__main__":
    try:
        logger.info("=" * 50)
        logger.info("Запуск SEMD Bot v2.0 (Полностью модульная архитектура)")
        logger.info("=" * 50)

        # Загружаем плагины в правильном порядке
        logger.info("Загрузка плагинов...")

        # 1. Root Menu - центральный маршрутизатор (ВСЕГДА ПЕРВЫЙ!)
        if core.load_plugin("plugins.root_menu"):
            logger.info("✓ Root Menu загружен")
        else:
            logger.error("✗ Ошибка загрузки Root Menu!")
            raise RuntimeError("Root Menu plugin failed to load")

        # 2. Публичные и 3. админские плагины; ошибка одного не мешает остальным.
        # WIP (отключены до завершения): plugins.admin_logs, plugins.plugin_manager
        plugins = [
            ("plugins.semd_checker", "SEMD Checker"),
            ("plugins.nsi_update_checker", "NSI Update Checker"),
            ("plugins.semd_reg_tracker", "SEMD Reg Tracker"),
            ("plugins.schematron_monitor", "Schematron Monitor"),
            ("plugins.statistics", "Statistics"),
        ]
        failed = []
        for plugin_path, title in plugins:
            if core.load_plugin(plugin_path):
                logger.info(f"✓ {title} загружен")
            else:
                logger.error(f"✗ Ошибка загрузки {title}")
                failed.append(title)

        if failed:
            logger.warning(f"Не загружены плагины: {', '.join(failed)}")
        else:
            logger.info("Все плагины загружены успешно!")
        logger.info("=" * 50)

        # Запускаем бота (включает планировщик и polling)
        core.start()

    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
        core.shutdown()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
        core.shutdown()
        raise

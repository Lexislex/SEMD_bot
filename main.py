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


if __name__ == '__main__':
    try:
        logger.info("=" * 50)
        logger.info("Запуск SEMD Bot v2.0 (Полностью модульная архитектура)")
        logger.info("=" * 50)

        # Загружаем плагины в правильном порядке
        logger.info("Загрузка плагинов...")

        # 1. Root Menu - центральный маршрутизатор (ВСЕГДА ПЕРВЫЙ!)
        if core.load_plugin('plugins.root_menu'):
            logger.info("✓ Root Menu загружен")
        else:
            logger.error("✗ Ошибка загрузки Root Menu!")
            raise RuntimeError("Root Menu plugin failed to load")

        # 2. Публичные плагины (доступны всем пользователям)
        if core.load_plugin('plugins.semd_checker'):
            logger.info("✓ SEMD Checker загружен")
        else:
            logger.error("✗ Ошибка загрузки SEMD Checker")

        if core.load_plugin('plugins.nsi_update_checker'):
            logger.info("✓ NSI Update Checker загружен")
        else:
            logger.error("✗ Ошибка загрузки NSI Update Checker")

        if core.load_plugin('plugins.semd_reg_tracker'):
            logger.info("✓ SEMD Reg Tracker загружен")
        else:
            logger.error("✗ Ошибка загрузки SEMD Reg Tracker")

        # 3. Админские плагины
        if core.load_plugin('plugins.statistics'):
            logger.info("✓ Statistics загружен")
        else:
            logger.error("✗ Ошибка загрузки Statistics")

        # WIP плагины (в разработке, отключены до завершения)
        # if core.load_plugin('plugins.admin_logs'):
        #     logger.info("✓ Admin Logs загружен")
        # else:
        #     logger.error("✗ Ошибка загрузки Admin Logs")

        # if core.load_plugin('plugins.plugin_manager'):
        #     logger.info("✓ Plugin Manager загружен")
        # else:
        #     logger.error("✗ Ошибка загрузки Plugin Manager")

        logger.info("Все плагины загружены успешно!")
        logger.info("=" * 50)

        # Запускаем бота (включает планировщик и polling)
        core.start()

    except KeyboardInterrupt:
        logger.info('Остановка по Ctrl+C')
        core.shutdown()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
        core.shutdown()
        raise

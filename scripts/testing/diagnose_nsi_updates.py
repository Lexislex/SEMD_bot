"""
Диагностика обновлений НСИ.

Запускает реальные запросы к FNSI и проверяет:
- наличие конфигурации
- доступность API
- корректность ответов
- полный цикл обновления через nsi_passport_updater
"""

import logging
import os
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from config import get_config
from plugins.nsi_update_checker.data import NSI_LIST
from plugins.semd_checker.semd_logic import SEMDVersionFetcher
from services.fnsi_client import get_version, nsi_passport_updater

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def check_config(cfg):
    """Проверяем обязательную конфигурацию."""
    logger.info("=== Проверка конфигурации ===")
    ok = True

    if not cfg.app.bot_token:
        logger.error("BOT_TOKEN не задан")
        ok = False
    else:
        logger.info(f"BOT_TOKEN: {'*' * 10}... (длина {len(cfg.app.bot_token)})")

    logger.info(f"ENV: {cfg.app.env}")
    logger.info(f"LOG_LEVEL: {cfg.app.log_level}")

    if not cfg.apis.fnsi_api_url:
        logger.error("FNSI_API_URL не задан")
        ok = False
    else:
        logger.info(f"FNSI_API_URL: {cfg.apis.fnsi_api_url}")

    if not cfg.apis.fnsi_api_key:
        logger.error("FNSI_API_KEY не задан")
        ok = False
    else:
        logger.info(f"FNSI_API_KEY: {'*' * 10}... (длина {len(cfg.apis.fnsi_api_key)})")

    if not cfg.apis.fnsi_files_url:
        logger.error("FNSI_FILES_URL не задан")
        ok = False
    else:
        logger.info(f"FNSI_FILES_URL: {cfg.apis.fnsi_files_url}")

    logger.info(f"FNSI_DB_PATH: {cfg.paths.fnsi_db_path}")
    logger.info(f"MZRF_CERT_PATH: {cfg.paths.mzrf_cert_path}")

    if not cfg.paths.mzrf_cert_path.exists():
        logger.error(f"Сертификат Минздрава НЕ НАЙДЕН: {cfg.paths.mzrf_cert_path}")
        ok = False
    else:
        logger.info(f"Сертификат найден: {cfg.paths.mzrf_cert_path}")

    if not cfg.paths.data_dir.exists():
        logger.warning(f"Директория данных не существует: {cfg.paths.data_dir}")
        try:
            cfg.paths.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Директория данных создана: {cfg.paths.data_dir}")
        except Exception as e:
            logger.error(f"Не удалось создать директорию данных: {e}")
            ok = False

    if not cfg.paths.fnsi_db_path.exists():
        logger.warning(f"БД FNSI не существует: {cfg.paths.fnsi_db_path}")
    else:
        logger.info(f"БД FNSI существует: {cfg.paths.fnsi_db_path}")

    logger.info(f"UPDS_MAILING_LIST: {cfg.accounts.updates_mailing_list}")
    return ok


def test_get_version(oid: str):
    """Тестируем получение версии справочника."""
    logger.info(f"=== Тест get_version для {oid} ===")
    try:
        info = get_version(oid)
        logger.info(
            f"Успех. Версия: {info.get('version')}, shortName: {info.get('shortName')}"
        )
        logger.debug(f"Полная информация: {info}")
        return True, info
    except Exception as e:
        logger.exception(f"Ошибка get_version для {oid}: {e}")
        return False, None


def test_nsi_passport_updater(oid: str):
    """Тестируем полный цикл обновления."""
    logger.info(f"=== Тест nsi_passport_updater для {oid} ===")
    try:
        updated, info = nsi_passport_updater(oid)
        logger.info(f"updated={updated}, info={info}")
        return updated, info
    except Exception as e:
        logger.exception(f"Ошибка nsi_passport_updater для {oid}: {e}")
        return False, None


def main():
    cfg = get_config()

    if not check_config(cfg):
        logger.error(
            "Конфигурация некорректна. Дальнейшие тесты могут не иметь смысла."
        )

    # Берём несколько справочников для проверки
    test_oids = NSI_LIST[:5]

    for oid in test_oids:
        print()
        ok, info = test_get_version(oid)
        if ok:
            test_nsi_passport_updater(oid)
        else:
            logger.error(
                f"Пропускаем nsi_passport_updater для {oid} из-за ошибки get_version"
            )

    print()
    logger.info("=== Диагностика завершена ===")


if __name__ == "__main__":
    main()

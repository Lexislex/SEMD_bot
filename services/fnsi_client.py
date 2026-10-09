# Настройка логирования
import logging
from datetime import datetime
from time import sleep
from typing import Optional

import requests

from config import get_config
from plugins.semd_checker.semd_logic import SEMDVersionFetcher
from services.proxy_utils import build_proxies, build_url
from utils.retry import backoff_delay

logger = logging.getLogger(__name__)

# Fallback-значения, если конфиг по какой-то причине недоступен
_DEFAULT_FNSI_REQUEST_TIMEOUT = 60  # секунд на одну попытку
_DEFAULT_FNSI_MAX_RETRIES = 3
_DEFAULT_FNSI_RETRY_DELAY = 2  # базовая задержка между попытками


def get_version(nsi: str, ver: str = "latest") -> dict:
    """
    Получает информацию о справочниках с официального сайта ФНСИ.

    Args:
        nsi: OID справочника
        ver: версия (по умолчанию 'latest')

    Returns:
        dict: информация о справочнике

    Raises:
        Exception: ошибки запроса или обработки ответа
    """
    cfg = get_config()

    if not cfg.apis.fnsi_api_key:
        raise ValueError("Отсутствует FNSI_API_KEY в конфигурации")

    if not cfg.paths.mzrf_cert_path:
        raise ValueError("Отсутствует MZRF_CERT в конфигурации")

    if not cfg.paths.mzrf_cert_path.exists():
        error_msg = (
            f"Сертификат Минздрава не найден: {cfg.paths.mzrf_cert_path}. "
            f"Выполните uv run python scripts/fetch_fnsi_cert.py"
        )
        logger.error(error_msg)
        raise ConnectionError(error_msg)

    request_timeout = getattr(
        cfg.apis, "fnsi_request_timeout", _DEFAULT_FNSI_REQUEST_TIMEOUT
    )
    max_retries = getattr(cfg.apis, "fnsi_max_retries", _DEFAULT_FNSI_MAX_RETRIES)

    headers = {
        "Accept": "application/json;charset=UTF-8",
        "Content-Type": "application/json",
    }
    session = requests.Session()
    url = (
        f"{build_url(cfg.apis.fnsi_api_url, 'searchDictionary')}"
        f"?userKey={cfg.apis.fnsi_api_key}&identifier={nsi}"
    )

    # Получаем настройки прокси для данного URL
    proxies = build_proxies(url)

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(
                url,
                headers=headers,
                verify=str(cfg.paths.mzrf_cert_path),
                timeout=request_timeout,
                proxies=proxies,
            )
            response.raise_for_status()
            logger.debug(f"Успешно получен ответ от ФНСИ для справочника {nsi}")
            break

        except requests.exceptions.Timeout as e:
            last_error = e
            logger.warning(
                f"Таймаут запроса к ФНСИ для справочника {nsi} (попытка {attempt}/{max_retries})"
            )
            if attempt < max_retries:
                sleep(backoff_delay(attempt, _DEFAULT_FNSI_RETRY_DELAY))

        except requests.exceptions.SSLError as e:
            error_msg = f"SSL ошибка при запросе к ФНСИ для справочника {nsi}: {e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)

        except requests.exceptions.ConnectionError as e:
            last_error = e
            logger.warning(
                f"Ошибка соединения с ФНСИ для справочника {nsi} (попытка {attempt}/{max_retries}): {e}"
            )
            if attempt < max_retries:
                sleep(backoff_delay(attempt, _DEFAULT_FNSI_RETRY_DELAY))

        except requests.exceptions.HTTPError as e:
            # 5xx ошибки ФНСИ часто временные — пробуем ещё раз
            status_code = e.response.status_code if e.response is not None else 0
            last_error = e
            if 500 <= status_code < 600 and attempt < max_retries:
                logger.warning(
                    f"HTTP {status_code} от ФНСИ для справочника {nsi} (попытка {attempt}/{max_retries})"
                )
                sleep(backoff_delay(attempt, _DEFAULT_FNSI_RETRY_DELAY))
            else:
                error_msg = f"Ошибка запроса к ФНСИ для {nsi}: {e}"
                logger.error(error_msg)
                raise ConnectionError(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"Ошибка запроса к ФНСИ для {nsi}: {e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)
    else:
        # Все попытки исчерпаны
        error_msg = (
            f"Не удалось получить ответ от ФНСИ для справочника {nsi} "
            f"после {max_retries} попыток: {last_error}"
        )
        logger.error(error_msg)
        raise ConnectionError(error_msg)

    # Проверяем, что ответ не пустой
    if not response.content:
        error_msg = f"Пустой ответ от ФНСИ для справочника {nsi}"
        raise ValueError(error_msg)

    try:
        response_data = response.json()
    except ValueError as e:
        error_msg = f"Невалидный JSON ответ от ФНСИ для {nsi}: {str(e)}"
        raise ValueError(error_msg)

    # Проверяем наличие и непустоту списка
    dictionary_list = response_data.get("list")
    if not dictionary_list or not isinstance(dictionary_list, list):
        error_msg = f"Ответ от ФНСИ для {nsi} не содержит списка справочников"
        raise ValueError(error_msg)

    try:
        data = dictionary_list[0]
    except IndexError:
        error_msg = f"ФНСИ вернул пустой список для справочника {nsi}"
        raise ValueError(error_msg)

    # Проверяем, что data не None и является словарем
    if data is None:
        error_msg = f"Ответ от ФНСИ для {nsi} равен None"
        raise ValueError(error_msg)

    if not isinstance(data, dict):
        error_msg = f"Ответ от ФНСИ для {nsi} не является словарем: {type(data)}"
        raise ValueError(error_msg)

    # Проверка обязательных полей в ответе
    required_fields = [
        "oid",
        "fullName",
        "shortName",
        "publishDate",
        "version",
        "releaseNotes",
    ]
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        error_msg = f"Отсутствуют обязательные поля в ответе ФНСИ для {nsi}: {', '.join(missing_fields)}"
        raise ValueError(error_msg)

    # Проверяем, что обязательные поля не None, кроме releaseNotes
    for field in required_fields:
        if field == "releaseNotes":
            # Для releaseNotes разрешаем None - обработаем позже
            continue
        if data.get(field) is None:
            error_msg = f"Поле '{field}' равно None в ответе ФНСИ для {nsi}"
            raise ValueError(error_msg)

    update = datetime.strptime(data["publishDate"], "%d.%m.%Y %H:%M")
    fnsi_info = {
        "id": data["oid"],
        "fullName": data["fullName"],
        "shortName": data["shortName"],
        "lastUpdate": update.isoformat(),
        "version": data["version"],
        "releaseNotes": data["releaseNotes"],
    }

    logger.info(
        f"Успешно получена информация для справочника {nsi}, версия {data['version']}"
    )
    return fnsi_info


def fetch_new_version(fnsi_oid: str) -> Optional[dict]:
    """
    Получает паспорт справочника из ФНСИ, если его версия новее известной.

    Ничего не сохраняет: паспорт записывается вызывающим кодом вместе с
    заданием на уведомление (см. services/notification_store.py), иначе сбой
    между записью паспорта и отправкой терял бы уведомление навсегда.

    Args:
        fnsi_oid: OID справочника

    Returns:
        dict с информацией о справочнике (id, fullName, shortName, lastUpdate,
        version, releaseNotes) или None, если версия не изменилась или
        произошла ошибка.
    """
    try:
        current_version = SEMDVersionFetcher(fnsi_oid).latest
        fnsi_info = get_version(fnsi_oid)

        if not fnsi_info or "version" not in fnsi_info:
            logger.warning(f"Невалидная информация от ФНСИ для справочника {fnsi_oid}")
            return None

        if current_version == fnsi_info["version"]:
            logger.debug(f"Обновлений для справочника {fnsi_oid} не найдено")
            return None
        return fnsi_info

    except (ConnectionError, ValueError) as e:
        logger.error(f"Ошибка при обновлении справочника {fnsi_oid}: {e}")
        return None

    except Exception as e:
        logger.error(f"Неожиданная ошибка при обновлении справочника {fnsi_oid}: {e}")
        logger.exception(f"Детали исключения для {fnsi_oid}")
        return None


if __name__ == "__main__":
    logger.warning("This module is not for direct call")
    exit(1)

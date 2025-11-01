import requests
import dateutil.parser as parser
from datetime import datetime
from typing import Tuple
from handlers.fnsi import fnsi_version
from handlers.sql import add_nsi_passport

from config import get_config
cfg = get_config()

# Настройка логирования
import logging
logger = logging.getLogger(__name__)

def get_version(nsi: str, ver: str = 'latest') -> dict:
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
    if not cfg.apis.fnsi_api_key:
        raise ValueError("Отсутствует FNSI_API_KEY в конфигурации")
    
    if not cfg.paths.mzrf_cert_path:
        raise ValueError("Отсутствует MZRF_CERT в конфигурации")

    headers = {
        'Accept': 'application/json;charset=UTF-8',
        'Content-Type': 'application/json'
    }
    session = requests.Session()
    url = f'{cfg.apis.fnsi_api_url}/searchDictionary'\
          f'?userKey={cfg.apis.fnsi_api_key}&identifier={nsi}'
    
    try:
        response = session.get(
            url, headers=headers,
            verify=cfg.paths.mzrf_cert_path,
            timeout=30  # Таймаут 30 секунд
        )
        response.raise_for_status()  # Проверка HTTP статуса
        
    except requests.exceptions.Timeout:
        error_msg = f"Таймаут запроса к ФНСИ для справочника {nsi}"
        raise ConnectionError(error_msg)
        
    except requests.exceptions.ConnectionError:
        error_msg = f"Ошибка соединения с ФНСИ для справочника {nsi}"
        raise ConnectionError(error_msg)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Ошибка запроса к ФНСИ для {nsi}: {str(e)}"
        raise ConnectionError(error_msg)
    
    # Проверяем, что ответ не пустой
    if not response.content:
        error_msg = f"Пустой ответ от ФНСИ для справочника {nsi}"
        raise ValueError(error_msg)
    
    try:
        data = response.json()['list'][0]
    except ValueError as e:
        error_msg = f"Невалидный JSON ответ от ФНСИ для {nsi}: {str(e)}"
        raise ValueError(error_msg)

    # Проверяем, что data не None и является словарем
    if data is None:
        error_msg = f"Ответ от ФНСИ для {nsi} равен None"
        raise ValueError(error_msg)
    
    if not isinstance(data, dict):
        error_msg = f"Ответ от ФНСИ для {nsi} не является словарем: {type(data)}"
        raise ValueError(error_msg)
    
    # Проверка обязательных полей в ответе
    required_fields = ['oid', 'fullName', 'shortName', 'publishDate', 'version', 'releaseNotes']
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        error_msg = f"Отсутствуют обязательные поля в ответе ФНСИ для {nsi}: {', '.join(missing_fields)}"
        raise ValueError(error_msg)
    
    # Проверяем, что обязательные поля не None, кроме releaseNotes
    for field in required_fields:
        if field == 'releaseNotes':
            # Для releaseNotes разрешаем None - обработаем позже
            continue
        if data.get(field) is None:
            error_msg = f"Поле '{field}' равно None в ответе ФНСИ для {nsi}"
            raise ValueError(error_msg)
    
    update = datetime.strptime(data['publishDate'], "%d.%m.%Y %H:%M")
    fnsi_info = {
        'id': data['oid'],
        'fullName': data['fullName'],
        'shortName': data['shortName'],
        'lastUpdate': update.isoformat(),
        'version': data['version'],
        'releaseNotes': data['releaseNotes'],
    }
    
    logger.info(f"Успешно получена информация для справочника {nsi}, версия {data['version']}")
    return fnsi_info

def nsi_passport_updater(fnsi_oid: str, vers: str = 'latest') -> Tuple[bool, dict]:
    """
    Обновляет паспорт справочника ФНСИ.

    Args:
        fnsi_oid: OID справочника
        vers: версия для проверки

    Returns:
        Tuple[bool, dict]:
            - bool: обновлен ли справочник
            - dict: информация о справочнике (если обновлен) или None (если нет/ошибка)
    """
    try:
        # Получаем информацию о текущей версии из базы
        fnsi = fnsi_version(fnsi_oid)

        # Проверяем, что объект fnsi не None
        if fnsi is None:
            logger.warning(f"Не удалось получить информацию о справочнике {fnsi_oid} из базы")
            return False, None

        # Получаем актуальную информацию с ФНСИ
        fnsi_info = get_version(fnsi_oid, vers)

        # Проверяем, что fnsi_info не None и содержит необходимые поля
        if not fnsi_info or 'version' not in fnsi_info:
            logger.warning(f"Невалидная информация от ФНСИ для справочника {fnsi_oid}")
            return False, None

        # Проверяем, есть ли обновление
        current_version = getattr(fnsi, 'latest', None)
        if current_version != fnsi_info['version']:
            # Пытаемся добавить новую версию в базу
            success = add_nsi_passport(fnsi_info)
            if success:
                logger.info(f"Успешно обновлен справочник {fnsi_oid} до версии {fnsi_info['version']}")
                return True, fnsi_info
            else:
                logger.error(f"Не удалось добавить справочник {fnsi_oid} в базу данных")
                return False, None
        else:
            logger.debug(f"Обновлений для справочника {fnsi_oid} не найдено")
            return False, None

    except (ConnectionError, ValueError) as e:
        logger.error(f"Ошибка при обновлении справочника {fnsi_oid}: {str(e)}")
        return False, None

    except Exception as e:
        logger.exception(f"Неожиданная ошибка при обновлении справочника {fnsi_oid}: {str(e)}")
        return False, None

if __name__ == '__main__':
    logger.warning('This module is not for direct call')
    exit(1)
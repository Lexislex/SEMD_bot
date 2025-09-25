import requests
import dateutil.parser as parser
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from handlers.fnsi import fnsi_version
from handlers.sql import add_nsi_passport
import logging
from config import get_config
# Настройка логирования
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

cfg = get_config()

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
        logger.error(error_msg)
        raise ConnectionError(error_msg)
        
    except requests.exceptions.ConnectionError:
        error_msg = f"Ошибка соединения с ФНСИ для справочника {nsi}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Ошибка запроса к ФНСИ для {nsi}: {str(e)}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)
    
    # Проверяем, что ответ не пустой
    if not response.content:
        error_msg = f"Пустой ответ от ФНСИ для справочника {nsi}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        data = response.json()['list'][0]
    except ValueError as e:
        error_msg = f"Невалидный JSON ответ от ФНСИ для {nsi}: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Проверяем, что data не None и является словарем
    if data is None:
        error_msg = f"Ответ от ФНСИ для {nsi} равен None"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    if not isinstance(data, dict):
        error_msg = f"Ответ от ФНСИ для {nsi} не является словарем: {type(data)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Проверка обязательных полей в ответе
    required_fields = ['oid', 'fullName', 'shortName', 'publishDate', 'version', 'releaseNotes']
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        error_msg = f"Отсутствуют обязательные поля в ответе ФНСИ для {nsi}: {', '.join(missing_fields)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Проверяем, что обязательные поля не None, кроме releaseNotes
    for field in required_fields:
        if field == 'releaseNotes':
            # Для releaseNotes разрешаем None - обработаем позже
            continue
        if data.get(field) is None:
            error_msg = f"Поле '{field}' равно None в ответе ФНСИ для {nsi}"
            logger.error(error_msg)
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

def format_releaseNotes(relNotes: Optional[str]) -> str:
    """
    Форматирует примечания к выпуску.
    
    Args:
        relNotes: сырые примечания к выпуску
    
    Returns:
        str: отформатированные примечания
    """
    if relNotes is None:
        return "Нет информации об изменениях"
    
    try:
        # Очистка строки
        cleaned_notes = relNotes.replace('\n', '').strip()
        if not cleaned_notes or cleaned_notes == ';':
            return "Нет информации об изменениях"
        
        # Удаляем завершающую точку с запятой если есть
        if cleaned_notes.endswith(';'):
            cleaned_notes = cleaned_notes[:-1]
        
        data = {}
        
        # Обрабатываем каждый элемент отдельно
        for item in cleaned_notes.split(';'):
            item = item.strip()
            if not item:
                continue
                
            # Разделяем только если есть двоеточие
            if ':' in item:
                parts = item.split(':', 1)  # Разделяем только по первому двоеточию
                key = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ''
                
                # Добавляем только если значение не '0'
                if value != '0':
                    data[key] = value
            else:
                # Если нет двоеточия, добавляем как ключ с пустым значением
                data[item] = ''
    
    except Exception as e:
        error_msg = f"Ошибка обработки изменений: {str(e)}"
        logger.error(f"{error_msg}, исходный текст: {relNotes}")
        return error_msg
    
    # Формируем результат
    if not data:
        return "Нет информации об изменениях"
    
    result_string = '\n'.join(
        f"{key}: {value}" if value else f"{key}" 
        for key, value in data.items()
    )
    return result_string

def nsi_passport_updater(fnsi_oid: str, vers: str = 'latest') -> Tuple[bool, str]:
    """
    Обновляет паспорт справочника ФНСИ.
    
    Args:
        fnsi_oid: OID справочника
        vers: версия для проверки
    
    Returns:
        Tuple[bool, str]: (обновлен ли справочник, сообщение о результате)
    """
    try:
        # Получаем информацию о текущей версии из базы
        fnsi = fnsi_version(fnsi_oid)

            # Проверяем, что объект fnsi не None
        if fnsi is None:
            error_msg = f"Не удалось получить информацию о справочнике {fnsi_oid} из базы"
            logger.error(error_msg)
            return False, error_msg
        
        # Получаем актуальную информацию с ФНСИ
        fnsi_info = get_version(fnsi_oid, vers)
        
        # Проверяем, что fnsi_info не None и содержит необходимые поля
        if not fnsi_info or 'version' not in fnsi_info:
            error_msg = f"Невалидная информация от ФНСИ для справочника {fnsi_oid}"
            logger.error(error_msg)
            return False, error_msg
        
        # # Дополнительная проверка всех обязательных полей
        # required_fields = ['id', 'fullName', 'shortName', 'lastUpdate', 'version', 'releaseNotes']
        # for field in required_fields:
        #     if field not in fnsi_info or fnsi_info[field] is None:
        #         error_msg = f"Отсутствует поле '{field}' в информации от ФНСИ для {fnsi_oid}"
        #         logger.error(error_msg)
        #         return False, error_msg
                
        # Проверяем, есть ли обновление
        current_version = getattr(fnsi, 'latest', None)
        if current_version != fnsi_info['version']:
            try:
                message = (
                    f"🆕 <b>Обновление версии</b>\n"
                    f"Справочник: {fnsi_info['shortName']}\n"
                    f"<a href='https://nsi.rosminzdrav.ru/dictionaries/"
                    f"{fnsi_info['id']}/passport/{fnsi_info['version']}'>"
                    f"{fnsi_info['id']}</a>\n"
                    f"версия: {fnsi_info['version']}\n"
                    f"от {(parser.parse(fnsi_info['lastUpdate'])).strftime('%H:%M %d.%m.%Y')}\n"
                    f"{format_releaseNotes(fnsi_info['releaseNotes'])}"
                )
                # Пытаемся добавить новую версию в базу
                success = add_nsi_passport(fnsi_info)
                if success:
                    logger.info(f"Успешно обновлен справочник {fnsi_oid} до версии {fnsi_info['version']}")
                    return True, message
                else:
                    error_msg = f"Не удалось добавить справочник {fnsi_oid} в базу данных"
                    logger.error(error_msg)
                    return False, error_msg
            except Exception as e:
                # Если возникла ошибка при формировании сообщения, НЕ добавляем в базу
                error_msg = f"Ошибка при формировании сообщения для справочника {fnsi_oid}: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
        else:
            logger.info(f"Обновлений для справочника {fnsi_oid} не найдено")
            return False, 'Обновлений нет'
            
    except (ConnectionError, ValueError) as e:
        error_msg = f"Ошибка при обновлении справочника {fnsi_oid}: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Неожиданная ошибка при обновлении справочника {fnsi_oid}: {str(e)}"
        logger.exception(error_msg)
        return False, error_msg

if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)
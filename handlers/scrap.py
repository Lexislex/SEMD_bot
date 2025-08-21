import requests
import dateutil.parser as parser
from handlers.fnsi import fnsi_version
from handlers.sql import add_nsi_passport
# подключаем модули для dotenv
from dotenv import dotenv_values
config = dotenv_values('.env')

def get_version(nsi: str, ver: str='latest') -> dict:
    """Эта функция получает информацию о справочниках с офиц. сайта ФНСИ.
    Отправляет на проверку наличия информации в базе. Если информации нет,
    то она добавляется.
    Если информация добавлена, то скачивается файл и распаковывается.

    Args:
        nsi_dict (dict): ключ - OID справочника, значение - список версий

    Returns:
    """

    s = requests.Session()
    url = f'https://nsi.rosminzdrav.ru/port/rest/passport'\
        f'?userKey={config["FNSI_API_KEY"]}&identifier={nsi}'
    r = s.get(url, verify=config['MZRF_CERT'])
    data = r.json()
    data['lastUpdate'] = parser.parse(data['lastUpdate']).isoformat()
    fnsi_info = {'id' : data['oid'], 'fullName' : data['fullName'],
                 'shortName' : data['shortName'],
                 'lastUpdate' : data['lastUpdate'],
                 'version' : data['version'],
                 'releaseNotes' : data['releaseNotes']}
    return fnsi_info

def format_releaseNotes(relNotes: str) -> str:
    if relNotes is None:
        return "Нет информации об изменениях"
    
    # Очистка строки
    cleaned_notes = relNotes.replace('\n', '').strip()
    if not cleaned_notes or cleaned_notes == ';':
        return "Нет информации об изменениях"
    
    # Удаляем завершающую точку с запятой если есть
    if cleaned_notes.endswith(';'):
        cleaned_notes = cleaned_notes[:-1]
    
    data = {}
    try:
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
        # В случае ошибки возвращаем исходный текст или сообщение об ошибке
        return f"Ошибка обработки изменений: {str(e)}"
    
    # Формируем результат
    if not data:
        return "Нет информации об изменениях"
    
    result_string = '\n'.join(
        f"{key}: {value}" if value else f"{key}" 
        for key, value in data.items()
    )
    return result_string

def nsi_passport_updater(fnsi_oid: str, vers='latest'):
    updated, message = False, 'Обновлений нет'
    fnsi = fnsi_version(fnsi_oid)
    fnsi_info = get_version(fnsi_oid, vers)
    if not fnsi.latest == fnsi_info['version']:
       if add_nsi_passport(fnsi_info):
        dt = parser.parse(fnsi_info['lastUpdate'])
        message = f"🆕 <b>Обновление версии</b>\n"\
            f"{dt.strftime("%H:%M %d.%m.%Y")}\n"\
            f"Справочник: "\
            f"{fnsi_info['shortName']}\n"\
            f"<a href='https://nsi.rosminzdrav.ru/dictionaries/"\
            f"{fnsi_info['id']}/passport/{fnsi_info['version']}'>{fnsi_info['id']}</a>\n"\
            f"версия: {fnsi_info['version']}\n\n"\
            f"{format_releaseNotes(fnsi_info['releaseNotes'])}"
        updated = True
    return updated, message
       


if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)
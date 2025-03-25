import requests
import dateutil.parser as parser
from handlers.fnsi import fnsi_version
from handlers.sql import add_nsi_passport
# подключаем модули для dotenv
from dotenv import dotenv_values
config = dotenv_values('.env')

def get_version(nsi: str, ver: str='latest') -> dict:
    """Эта функция получает информацию о справочниках с офиц. сайта ФНСИ.
    Отправляет на проверку наличия информации в базе. Если информации нет, то она добавляется.
    Если информация добавлена, то скачивается файл и распаковывается.

    Args:
        nsi_dict (dict): ключ - OID справочника, значение - список версий

    Returns:
    """

    s = requests.Session()
    url = f'https://nsi.rosminzdrav.ru/port/rest/passport?userKey={config["FNSI_API_KEY"]}&identifier={nsi}'
    r = s.get(url, verify=config['MZRF_CERT'])
    data = r.json()
    data['lastUpdate'] = parser.parse(data['lastUpdate']).isoformat()
    fnsi_info = {'id' : data['oid'], 'fullName' : data['fullName'], 'shortName' : data['shortName'], 
                    'lastUpdate' : data['lastUpdate'], 'version' : data['version'], 
                    'releaseNotes' : data['releaseNotes']}
    return fnsi_info

def format_releaseNotes(relNotes:str) -> str:
    data = dict(map(lambda x: x.split(': '), relNotes.replace('\n','')[:-1].split(';')))
    filtered_data = {key: value for key, value in data.items() if value != '0'}
    result_string = '\n'.join(f"{key}: {value}" for key, value in filtered_data.items())
    return result_string

def nsi_passport_updater(fnsi_oid: str, vers='latest'):
    updated, message = False, 'Обновлений нет'
    fnsi = fnsi_version(fnsi_oid)
    fnsi_info = get_version(fnsi_oid, vers)
    if not fnsi.latest == fnsi_info['version']:
       if add_nsi_passport(fnsi_info):
        message = f"🆕 <b>Обновление версии</b>\nСправочник: {fnsi_info['shortName']} \
<a href='https://nsi.rosminzdrav.ru/dictionaries/{fnsi_info['id']}/passport/{fnsi_info['version']}'>🔗</a>\n\
версия: {fnsi_info['version']}\n\n{format_releaseNotes(fnsi_info['releaseNotes'])}"
        updated = True
    return updated, message
       


if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)

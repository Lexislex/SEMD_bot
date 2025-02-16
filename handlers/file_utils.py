import os
import requests
# подключаем модули для dotenv
from dotenv import dotenv_values
config = dotenv_values('.env')

def download_file(nsi:str, ver: str, path: str=config['FILES_PATH']) -> bool:
    """ Эта функция удаляет все файлы в папке и скачивает необходимый архив со справочником в заданную папку.

    Args:
        nsi (str): OID справочника
        ver (str): версия справочника

    Returns:
        bool: True, если скачан успешно, Folse, если нет.
    """
    out_file_name = f'{nsi}_{ver}_csv.zip'
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0) Gecko/20100101 Firefox/45.0'
        })
    if os.path.exists(path + out_file_name): return True
    try:
        # Удаляем все файлы в папке
        for file_name in os.listdir(path):
            file = path + file_name
            if os.path.isfile(file):
                os.remove(file)
        # Скачиваем файл
        with open(os.path.join(path + out_file_name), 'wb') as out_stream:
            req = requests.get('https://nsi.rosminzdrav.ru/api/dataFiles/' + out_file_name,
                               stream=True, verify=config['MZRF_CERT'])
            for chunk in req.iter_content(1024):  # Куски по 1 КБ
                out_stream.write(chunk)
        return True
    except Exception as e:
        print('Warning:', e)
        return False
    
if __name__ == '__main__':
    print('This module is not for direct call')
    exit(1)
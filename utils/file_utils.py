import os
import glob
import requests
# подключаем модули для dotenv
from config import get_config
from services.proxy_utils import build_proxies
cfg = get_config()

# Настройка логирования
import logging
logger = logging.getLogger(__name__)

def download_file(nsi:str, ver: str, path: str=cfg.paths.files_dir) -> bool:
    """ Эта функция удаляет все версии справочника в папке и скачивает
    необходимый архив со справочником в заданную папку.

    Args:
        nsi (str): OID справочника
        ver (str): версия справочника

    Returns:
        bool: True, если скачан успешно, False, если нет.
    """
    out_file_name = f'{nsi}_{ver}_csv.zip'
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0)'\
        ' Gecko/20100101 Firefox/45.0'
        })
    if os.path.exists(os.path.join(path, out_file_name)):
        return True
    try:
        # Удаляем предыдущие версии справочника
        for f in glob.glob(f'{path}{nsi}*.zip'):
            os.remove(f)

        # Формируем URL для скачивания
        download_url = f'{cfg.apis.fnsi_files_url}/{out_file_name}'

        # Получаем настройки прокси для данного URL
        proxies = build_proxies(download_url)

        # Скачиваем файл
        with open(os.path.join(path, out_file_name), 'wb') as out_stream:
            req = requests.get(
                download_url,
                stream=True,
                verify=cfg.paths.mzrf_cert_path,
                proxies=proxies)
            if req.status_code != 200:
                raise FileNotFoundError(req.json()['resultText'])
            # Скачиваем файл в папку
            for chunk in req.iter_content(1024):  # Куски по 1 КБ
                out_stream.write(chunk)
        return True
    except Exception as e:
        logger.warning(f'Warning: {e}')
        if os.path.exists(os.path.join(path, out_file_name)):
            os.remove(os.path.join(path, out_file_name))
        return False
    
if __name__ == '__main__':
    logger.warning('This module is not for direct call')
    exit(1)
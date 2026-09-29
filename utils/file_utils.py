import glob
import os

import requests

# подключаем модули для dotenv
from config import get_config
from services.proxy_utils import build_proxies, build_url

cfg = get_config()

# Настройка логирования
import logging

logger = logging.getLogger(__name__)


def download_file(nsi: str, ver: str, path: str = cfg.paths.files_dir) -> bool:
    """Эта функция удаляет все версии справочника в папке и скачивает
    необходимый архив со справочником в заданную папку.

    Args:
        nsi (str): OID справочника
        ver (str): версия справочника

    Returns:
        bool: True, если скачан успешно, False, если нет.
    """
    out_file_name = f"{nsi}_{ver}_csv.zip"
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0)"
            " Gecko/20100101 Firefox/45.0"
        }
    )
    if os.path.exists(os.path.join(path, out_file_name)):
        return True
    try:
        # Удаляем предыдущие версии справочника
        for f in glob.glob(f"{path}{nsi}*.zip"):
            os.remove(f)

        # Проверяем наличие сертификата
        if not cfg.paths.mzrf_cert_path.exists():
            logger.error(
                f"Сертификат Минздрава не найден: {cfg.paths.mzrf_cert_path}. "
                f"Выполните poetry run python scripts/fetch_fnsi_cert.py"
            )
            return False

        # Формируем URL для скачивания без двойного слеша
        download_url = build_url(cfg.apis.fnsi_files_url, out_file_name)

        # Получаем настройки прокси для данного URL
        proxies = build_proxies(download_url)

        # Скачиваем файл
        with open(os.path.join(path, out_file_name), "wb") as out_stream:
            req = requests.get(
                download_url,
                stream=True,
                verify=str(cfg.paths.mzrf_cert_path),
                proxies=proxies,
            )
            if req.status_code != 200:
                try:
                    error_text = req.json().get("resultText", req.text)
                except ValueError:
                    error_text = req.text
                raise FileNotFoundError(error_text)
            # Скачиваем файл в папку
            for chunk in req.iter_content(1024):  # Куски по 1 КБ
                out_stream.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка скачивания файла {out_file_name}: {e}")
        if os.path.exists(os.path.join(path, out_file_name)):
            os.remove(os.path.join(path, out_file_name))
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при скачивании файла {out_file_name}: {e}")
        if os.path.exists(os.path.join(path, out_file_name)):
            os.remove(os.path.join(path, out_file_name))
        return False


if __name__ == "__main__":
    logger.warning("This module is not for direct call")
    exit(1)

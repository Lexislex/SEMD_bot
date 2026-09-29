import glob
import logging
import os

import requests

from config import get_config
from services.proxy_utils import build_proxies, build_url

cfg = get_config()

logger = logging.getLogger(__name__)


def _remove_other_versions(nsi: str, path: str, keep: str) -> None:
    """Remove downloaded archives of other versions of the same dictionary."""
    # "_" после OID: иначе шаблон 1.2.643.5.1.13.13.99.2.63* зацепит и ...2.638
    for f in glob.glob(os.path.join(path, f"{glob.escape(nsi)}_*_csv.zip")):
        if os.path.basename(f) != keep:
            try:
                os.remove(f)
            except OSError as e:
                logger.warning(f"Не удалось удалить старую версию {f}: {e}")


def download_file(nsi: str, ver: str, path: str = cfg.paths.files_dir) -> bool:
    """Скачивает архив справочника в заданную папку и удаляет его прежние версии.

    Args:
        nsi (str): OID справочника
        ver (str): версия справочника
        path (str): папка для архивов

    Returns:
        bool: True, если файл есть или скачан успешно, False, если нет.
    """
    path = str(path)
    out_file_name = f"{nsi}_{ver}_csv.zip"
    out_path = os.path.join(path, out_file_name)
    if os.path.exists(out_path):
        return True
    try:
        # Проверяем наличие сертификата
        if not cfg.paths.mzrf_cert_path.exists():
            logger.error(
                f"Сертификат Минздрава не найден: {cfg.paths.mzrf_cert_path}. "
                f"Выполните uv run python scripts/fetch_fnsi_cert.py"
            )
            return False

        # Формируем URL для скачивания без двойного слеша
        download_url = build_url(cfg.apis.fnsi_files_url, out_file_name)

        req = requests.get(
            download_url,
            stream=True,
            verify=str(cfg.paths.mzrf_cert_path),
            proxies=build_proxies(download_url),
            timeout=cfg.apis.fnsi_request_timeout,
        )
        if req.status_code != 200:
            try:
                error_text = req.json().get("resultText", req.text)
            except ValueError:
                error_text = req.text
            raise FileNotFoundError(error_text)

        with open(out_path, "wb") as out_stream:
            for chunk in req.iter_content(1024):  # Куски по 1 КБ
                out_stream.write(chunk)

        # Старые версии удаляем только после успешной загрузки новой
        _remove_other_versions(nsi, path, keep=out_file_name)
        return True
    except Exception as e:
        logger.error(f"Ошибка скачивания файла {out_file_name}: {e}")
        if os.path.exists(out_path):
            os.remove(out_path)
        return False


if __name__ == "__main__":
    logger.warning("This module is not for direct call")
    exit(1)

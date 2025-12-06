"""
Утилиты для работы с прокси-серверами.
"""
from typing import Optional, Dict
from config import get_config

# Настройка логирования
import logging
logger = logging.getLogger(__name__)


def build_proxies(url: str = None) -> Optional[Dict[str, str]]:
    """
    Формирует словарь с настройками прокси для requests только для nsi.rosminzdrav.ru.

    Args:
        url: URL запроса для проверки домена (опционально)

    Returns:
        Dict[str, str] или None: словарь с прокси или None, если прокси отключены
                                  или URL не относится к nsi.rosminzdrav.ru
    """
    cfg = get_config()

    if not cfg.proxy.enabled:
        return None

    # Проверяем, что URL относится к nsi.rosminzdrav.ru
    if url and 'nsi.rosminzdrav.ru' not in url:
        logger.debug(f"Прокси не используется для {url} (не nsi.rosminzdrav.ru)")
        return None

    if not cfg.proxy.host or not cfg.proxy.port:
        logger.warning("Прокси включен, но не указан хост или порт")
        return None

    # Формируем URL прокси
    proxy_auth = ""
    if cfg.proxy.user and cfg.proxy.password:
        proxy_auth = f"{cfg.proxy.user}:{cfg.proxy.password}@"

    proxy_url = f"{cfg.proxy.proxy_type}://{proxy_auth}{cfg.proxy.host}:{cfg.proxy.port}"

    # Возвращаем словарь для http и https
    proxies = {
        'http': proxy_url,
        'https': proxy_url,
    }

    logger.info(f"Используется прокси для nsi.rosminzdrav.ru: {cfg.proxy.proxy_type}://{cfg.proxy.host}:{cfg.proxy.port}")
    return proxies


if __name__ == '__main__':
    logger.warning('This module is not for direct call')
    exit(1)

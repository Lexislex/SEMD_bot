#!/usr/bin/env python3
"""
Скрипт для получения и проверки бесплатных прокси-серверов.

Этот скрипт загружает списки бесплатных прокси из различных источников,
проверяет их работоспособность и выводит работающие прокси.

Использование:
    python scripts/fetch_free_proxies.py [--test-url URL] [--timeout SECONDS] [--max-proxies N]

Аргументы:
    --test-url URL      URL для проверки прокси (по умолчанию: https://nsi.rosminzdrav.ru)
    --timeout SECONDS   Таймаут для проверки прокси в секундах (по умолчанию: 10)
    --max-proxies N     Максимальное количество прокси для проверки (по умолчанию: 50)
"""

import requests
import argparse
import sys
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_proxyscrape_proxies(protocol: str = 'http', timeout: int = 10000, country: str = 'all') -> List[str]:
    """
    Получает список прокси с ProxyScrape API.

    Args:
        protocol: Протокол прокси (http, socks4, socks5)
        timeout: Таймаут прокси в миллисекундах
        country: Код страны или 'all'

    Returns:
        List[str]: список прокси в формате IP:PORT
    """
    try:
        url = f"https://api.proxyscrape.com/v2/?request=get&protocol={protocol}&timeout={timeout}&country={country}&ssl=all&anonymity=all"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        proxies = response.text.strip().split('\n')
        proxies = [p.strip() for p in proxies if p.strip()]
        print(f"[ProxyScrape] Получено {len(proxies)} прокси")
        return proxies
    except Exception as e:
        print(f"[ProxyScrape] Ошибка получения прокси: {e}")
        return []


def fetch_geonode_proxies(protocol: str = 'http', limit: int = 50) -> List[str]:
    """
    Получает список прокси с Geonode API.

    Args:
        protocol: Протокол прокси (http, socks4, socks5)
        limit: Максимальное количество прокси

    Returns:
        List[str]: список прокси в формате IP:PORT
    """
    try:
        url = f"https://proxylist.geonode.com/api/proxy-list?protocols={protocol}&limit={limit}&page=1&sort_by=lastChecked&sort_type=desc"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        proxies = [f"{p['ip']}:{p['port']}" for p in data.get('data', [])]
        print(f"[Geonode] Получено {len(proxies)} прокси")
        return proxies
    except Exception as e:
        print(f"[Geonode] Ошибка получения прокси: {e}")
        return []


def test_proxy(proxy: str, test_url: str, timeout: int, proxy_type: str = 'http') -> Tuple[bool, str, Optional[float]]:
    """
    Проверяет работоспособность прокси.

    Args:
        proxy: Прокси в формате IP:PORT
        test_url: URL для проверки
        timeout: Таймаут в секундах
        proxy_type: Тип прокси (http, https, socks5)

    Returns:
        Tuple[bool, str, Optional[float]]: (работает, прокси, время ответа)
    """
    proxy_url = f"{proxy_type}://{proxy}"
    proxies = {
        'http': proxy_url,
        'https': proxy_url,
    }

    try:
        start = requests.utils.default_headers()
        response = requests.get(
            test_url,
            proxies=proxies,
            timeout=timeout,
            verify=False  # Отключаем проверку SSL для тестирования
        )

        if response.status_code == 200:
            return (True, proxy, response.elapsed.total_seconds())
        else:
            return (False, proxy, None)
    except Exception:
        return (False, proxy, None)


def main():
    parser = argparse.ArgumentParser(
        description='Получение и проверка бесплатных прокси-серверов'
    )
    parser.add_argument(
        '--test-url',
        default='https://httpbin.org/ip',
        help='URL для проверки прокси (по умолчанию: https://httpbin.org/ip)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=10,
        help='Таймаут для проверки прокси в секундах (по умолчанию: 10)'
    )
    parser.add_argument(
        '--max-proxies',
        type=int,
        default=50,
        help='Максимальное количество прокси для проверки (по умолчанию: 50)'
    )
    parser.add_argument(
        '--proxy-type',
        default='http',
        choices=['http', 'https', 'socks5'],
        help='Тип прокси (по умолчанию: http)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=10,
        help='Количество потоков для проверки (по умолчанию: 10)'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Получение списков бесплатных прокси...")
    print("=" * 70)

    # Получаем прокси из различных источников
    all_proxies = []
    all_proxies.extend(fetch_proxyscrape_proxies(protocol=args.proxy_type))
    all_proxies.extend(fetch_geonode_proxies(protocol=args.proxy_type, limit=args.max_proxies))

    # Удаляем дубликаты
    all_proxies = list(set(all_proxies))

    # Ограничиваем количество прокси
    all_proxies = all_proxies[:args.max_proxies]

    print(f"\nВсего уникальных прокси для проверки: {len(all_proxies)}")

    if not all_proxies:
        print("\nНе удалось получить прокси. Попробуйте позже.")
        sys.exit(1)

    print("=" * 70)
    print(f"Проверка прокси (URL: {args.test_url}, таймаут: {args.timeout}s)...")
    print("=" * 70)

    working_proxies = []
    checked = 0

    # Проверяем прокси параллельно
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_proxy = {
            executor.submit(test_proxy, proxy, args.test_url, args.timeout, args.proxy_type): proxy
            for proxy in all_proxies
        }

        for future in as_completed(future_to_proxy):
            checked += 1
            success, proxy, response_time = future.result()

            if success:
                working_proxies.append((proxy, response_time))
                print(f"✓ [{checked}/{len(all_proxies)}] {proxy} - работает (время ответа: {response_time:.2f}s)")
            else:
                print(f"✗ [{checked}/{len(all_proxies)}] {proxy} - не работает", end='\r')

    print("\n")
    print("=" * 70)
    print(f"Результаты проверки")
    print("=" * 70)
    print(f"Всего проверено: {checked}")
    print(f"Работающих прокси: {len(working_proxies)}")

    if working_proxies:
        # Сортируем по времени ответа
        working_proxies.sort(key=lambda x: x[1])

        print("\nРаботающие прокси (отсортированы по скорости):")
        print("-" * 70)
        for i, (proxy, response_time) in enumerate(working_proxies[:10], 1):
            host, port = proxy.split(':')
            print(f"{i}. {proxy} (время ответа: {response_time:.2f}s)")
            print(f"   Для .env файла:")
            print(f"   PROXY_ENABLED=true")
            print(f"   PROXY_TYPE={args.proxy_type}")
            print(f"   PROXY_HOST={host}")
            print(f"   PROXY_PORT={port}")
            print()
    else:
        print("\nРаботающие прокси не найдены.")
        print("Попробуйте:")
        print("  1. Увеличить --timeout")
        print("  2. Увеличить --max-proxies")
        print("  3. Изменить --proxy-type")
        print("  4. Использовать платные прокси-сервисы")

    print("=" * 70)


if __name__ == '__main__':
    # Отключаем предупреждения SSL
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    main()

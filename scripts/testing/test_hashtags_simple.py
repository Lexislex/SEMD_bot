#!/usr/bin/env python3
"""Простой тест формирования хэштегов без зависимостей."""

import re
import dateutil.parser as parser

def get_hashtags(fnsi_info: dict, nsi_oid: str) -> str:
    """
    Генерирует хэштеги для сообщения (копия функции из formatters.py).

    Args:
        fnsi_info: информация о справочнике
        nsi_oid: OID справочника

    Returns:
        Строка с хэштегами
    """
    tags = []

    try:
        # Название справочника (очищаем от специальных символов)
        name = fnsi_info.get('shortName', '')[:20]
        if name:
            clean_name = re.sub(r'[^\w]', '_', name, flags=re.UNICODE)
            tags.append(f"#{clean_name}")

        # Месяц и год
        try:
            last_update = parser.parse(fnsi_info.get('lastUpdate', ''))
            month_names = [
                'янв', 'фев', 'мар', 'апр', 'май', 'июн',
                'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'
            ]
            month_name = month_names[last_update.month - 1]
            year = last_update.year
            tags.append(f"#{month_name}{year}")
        except:
            pass

    except Exception as e:
        print(f"Ошибка при генерировании хэштегов: {e}")

    return ' '.join(tags) if tags else ''


# Тестовые данные с различными символами
test_cases = [
    {
        'name': 'Справочник МКБ-10',
        'data': {
            'shortName': 'Справочник МКБ-10',
            'lastUpdate': '2025-03-15T10:30:00',
            'id': '1.2.643.5.1.13.13.11.1005',
        }
    },
    {
        'name': 'Медицинские услуги (A01.01.001)',
        'data': {
            'shortName': 'Медицинские услуги (A01.01.001)',
            'lastUpdate': '2024-12-25T18:45:00',
            'id': '1.2.643.5.1.13.13.11.1070',
        }
    },
    {
        'name': 'Лекарственные препараты / ЕСКЛП',
        'data': {
            'shortName': 'Лекарственные препараты / ЕСКЛП',
            'lastUpdate': '2025-01-10T09:15:00',
            'id': '1.2.643.5.1.13.13.11.1367',
        }
    },
    {
        'name': 'Справочник с пробелами, точками и #спецсимволами!',
        'data': {
            'shortName': 'Справочник с пробелами, точками и #спецсимволами!',
            'lastUpdate': '2025-02-20T14:20:00',
            'id': '1.2.643.5.1.13.13.99.9999',
        }
    },
    {
        'name': 'Очень длинное название справочника которое должно обрезаться',
        'data': {
            'shortName': 'Очень длинное название справочника которое должно обрезаться',
            'lastUpdate': '2025-11-03T12:00:00',
            'id': '1.2.643.5.1.13.13.11.1234',
        }
    },
    {
        'name': 'Пустое название',
        'data': {
            'shortName': '',
            'lastUpdate': '2025-05-05T10:00:00',
            'id': '1.2.643.5.1.13.13.11.0000',
        }
    },
    {
        'name': 'Русские буквы и цифры 123',
        'data': {
            'shortName': 'Русские буквы и цифры 123',
            'lastUpdate': '2025-06-10T15:30:00',
            'id': '1.2.643.5.1.13.13.11.5555',
        }
    }
]

def test_hashtags():
    """Тестирует формирование хэштегов."""
    print("=" * 80)
    print("ТЕСТ ФОРМИРОВАНИЯ ХЭШТЕГОВ")
    print("=" * 80)
    print()

    for i, test_case in enumerate(test_cases, 1):
        test_data = test_case['data']
        print(f"Тест #{i}: {test_case['name']}")
        print(f"Название: '{test_data['shortName']}'")
        print(f"Дата: {test_data['lastUpdate']}")

        hashtags = get_hashtags(test_data, test_data['id'])
        print(f"Результат: {hashtags}")

        # Проверяем, что хэштеги валидные
        if hashtags:
            tags = hashtags.split()
            all_valid = True
            for tag in tags:
                if not tag.startswith('#'):
                    print(f"  ⚠️  ОШИБКА: хэштег не начинается с #: {tag}")
                    all_valid = False
                elif ' ' in tag:
                    print(f"  ⚠️  ОШИБКА: пробел в хэштеге: {tag}")
                    all_valid = False
                elif any(c in tag for c in '.,;:!?()[]{}/<>-'):
                    print(f"  ⚠️  ОШИБКА: спецсимволы в хэштеге: {tag}")
                    all_valid = False

            if all_valid:
                print(f"  ✓ Все хэштеги валидны: {len(tags)} шт.")
        else:
            print("  (нет хэштегов)")

        print("-" * 80)
        print()

if __name__ == '__main__':
    test_hashtags()

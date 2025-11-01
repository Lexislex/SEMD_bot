"""
Форматеры сообщений об обновлении справочников НСИ.

Каждый форматер создает сообщение определенного стиля для уведомления об обновлении.
Поддерживает интеллектуальное определение режима отправки (со звуком/без) и добавление хэштегов.
"""

from abc import ABC, abstractmethod
import logging
import dateutil.parser as parser
from typing import Optional
from datetime import datetime
from utils.text_formatters import format_releaseNotes


class UpdateMessageFormatter(ABC):
    """Абстрактный класс для форматирования сообщений об обновлении."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def format(self, fnsi_info: dict) -> str:
        """
        Форматирует сообщение об обновлении справочника.

        Args:
            fnsi_info: информация о справочнике (dict)

        Returns:
            str: отформатированное HTML сообщение
        """
        pass

    def should_send_silent(self, nsi_oid: str, current_hour: Optional[int] = None) -> bool:
        """
        Определяет, нужно ли отправлять уведомление без звука.

        Args:
            nsi_oid: OID справочника
            current_hour: текущий час (0-23), если None - берется текущее время

        Returns:
            True если нужно отправить тихое уведомление
        """
        if current_hour is None:
            current_hour = datetime.now().hour

        # Ночью всегда без звука (22:00 - 08:00)
        if current_hour >= 22 or current_hour < 8:
            return True

        return False

    def get_hashtags(self, fnsi_info: dict, nsi_oid: str) -> str:
        """
        Генерирует хэштеги для сообщения.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника

        Returns:
            Строка с хэштегами
        """
        tags = []

        try:
            # Название справочника (очищаем от специальных символов)
            name = fnsi_info.get('shortName', '').replace(' ', '_').replace('/', '_')[:20]
            if name:
                tags.append(f"#{name}")

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
            self.logger.debug(f"Ошибка при генерировании хэштегов: {e}")

        return ' '.join(tags) if tags else ''


class ImportantUpdateFormatter(UpdateMessageFormatter):
    """
    Форматер для важных обновлений.
    Используется для справочников, влияющих на критичные системы.
    Включает полную информацию и хэштеги.
    """

    def format(self, fnsi_info: dict, nsi_oid: str = None) -> str:
        """
        Форматирует важное обновление с выделением и полной информацией.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника (для хэштегов)
        """
        try:
            nsi_oid = nsi_oid or fnsi_info.get('id', '')
            url = (
                f"https://nsi.rosminzdrav.ru/dictionaries/"
                f"{fnsi_info['id']}/passport/{fnsi_info['version']}"
            )
            date_str = (parser.parse(fnsi_info['lastUpdate'])).strftime('%H:%M %d.%m.%Y')
            hashtags = self.get_hashtags(fnsi_info, nsi_oid)

            message = (
                f"⚠️ <b>Важное обновление</b>\n\n"
                f"📋 <b>{fnsi_info['shortName']}</b>\n"
                f"ID: <code>{fnsi_info['id']}</code>\n"
                f"Версия: <code>{fnsi_info['version']}</code>\n"
                f"Время: {date_str}\n"
                f"\n💡 <i>Описание изменений:</i>\n"
                f"<i>{format_releaseNotes(fnsi_info['releaseNotes'])}</i>\n"
                f"\n🔗 <a href='{url}'>Перейти к справочнику</a>"
            )

            if hashtags:
                message += f"\n\n{hashtags}"

            return message
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании критического обновления: {e}")
            return (
                f"⚠️ <b>Важное обновление</b>\n"
                f"Справочник: <b>{fnsi_info.get('shortName', 'Unknown')}</b>\n"
                f"Версия: <code>{fnsi_info.get('version', 'Unknown')}</code>\n"
            )
class DefaultUpdateFormatter(UpdateMessageFormatter):
    """
    Форматер для важных обновлений.
    Используется для справочников, влияющих на критичные системы.
    Включает полную информацию и хэштеги.
    """

    def format(self, fnsi_info: dict, nsi_oid: str = None) -> str:
        """
        Форматирует важное обновление с выделением и полной информацией.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника (для хэштегов)
        """
        try:
            nsi_oid = nsi_oid or fnsi_info.get('id', '')
            url = (
                f"https://nsi.rosminzdrav.ru/dictionaries/"
                f"{fnsi_info['id']}/passport/{fnsi_info['version']}"
            )
            date_str = (parser.parse(fnsi_info['lastUpdate'])).strftime('%H:%M %d.%m.%Y')
            hashtags = self.get_hashtags(fnsi_info, nsi_oid)

            message = (
                f"🔄 <b>Обновление справочника</b>\n\n"
                f"📋 <b>{fnsi_info['shortName']}</b>\n"
                f"ID: <code>{fnsi_info['id']}</code>\n"
                f"Версия: <code>{fnsi_info['version']}</code>\n"
                f"Время: {date_str}\n"
                f"\n💡 <i>Описание изменений:</i>\n"
                f"<i>{format_releaseNotes(fnsi_info['releaseNotes'])}</i>\n"
                f"\n🔗 <a href='{url}'>Перейти к справочнику</a>"
            )

            if hashtags:
                message += f"\n\n{hashtags}"

            return message
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании критического обновления: {e}")
            return (
                f"🔄 <b>Обновление справочника</b>\n"
                f"Справочник: <b>{fnsi_info.get('shortName', 'Unknown')}</b>\n"
                f"Версия: <code>{fnsi_info.get('version', 'Unknown')}</code>\n"
            )


class MinorUpdateFormatter(UpdateMessageFormatter):
    """
    Форматер для обычных обновлений.
    Укороченный формат для часто обновляемых справочников.
    """

    def format(self, fnsi_info: dict, nsi_oid: str = None) -> str:
        """
        Форматирует обновление в укороченном виде.
        Подходит для справочников, которые обновляются часто.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника (для хэштегов)
        """
        try:
            nsi_oid = nsi_oid or fnsi_info.get('id', '')
            url = (
                f"https://nsi.rosminzdrav.ru/dictionaries/"
                f"{fnsi_info['id']}/passport/{fnsi_info['version']}"
            )

            message = (
                f"📝 <b>{fnsi_info['shortName']}</b> v{fnsi_info['version']}\n"
                f"   <a href='{url}'>↗ {fnsi_info['id']}</a>"
            )

            return message
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании обновления: {e}")
            return (
                f"📝 <b>{fnsi_info.get('shortName', 'Unknown')}</b> "
                f"v{fnsi_info.get('version', 'Unknown')}"
            )

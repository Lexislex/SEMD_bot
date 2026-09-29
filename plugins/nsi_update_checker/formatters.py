"""
Форматеры сообщений об обновлении справочников НСИ.

Каждый форматер создает сообщение определенного стиля для уведомления об обновлении.
Поддерживает определение режима отправки (со звуком/без) и добавление хэштегов.
Все данные ФНСИ экранируются: сообщения отправляются с parse_mode=html.
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from html import escape
from typing import Optional

import dateutil.parser as parser

from utils.text_formatters import format_releaseNotes

MONTH_TAGS = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]  # fmt: skip


def passport_url(fnsi_info: dict) -> str:
    """Link to the dictionary passport of the given version."""
    return (
        f"https://nsi.rosminzdrav.ru/dictionaries/"
        f"{fnsi_info['id']}/passport/{fnsi_info['version']}"
    )


class UpdateMessageFormatter(ABC):
    """Абстрактный класс для форматирования сообщений об обновлении."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def format(self, fnsi_info: dict, nsi_oid: Optional[str] = None) -> str:
        """
        Форматирует сообщение об обновлении справочника.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника

        Returns:
            str: отформатированное HTML сообщение
        """

    def should_send_silent(
        self, nsi_oid: str, current_hour: Optional[int] = None
    ) -> bool:
        """
        Определяет, нужно ли отправлять уведомление без звука.

        Args:
            nsi_oid: OID справочника
            current_hour: текущий час (0-23), если None - берется текущее время

        Returns:
            True если нужно отправить тихое уведомление (ночью, 22:00 - 08:00)
        """
        if current_hour is None:
            current_hour = datetime.now().hour
        return current_hour >= 22 or current_hour < 8

    def get_hashtags(self, fnsi_info: dict, nsi_oid: str) -> str:
        """
        Генерирует хэштеги для сообщения: название справочника и месяц обновления.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника

        Returns:
            Строка с хэштегами
        """
        tags = []

        name = (fnsi_info.get("shortName") or "")[:20]
        if name:
            tags.append("#" + re.sub(r"[^\w]", "_", name, flags=re.UNICODE))

        try:
            last_update = parser.parse(fnsi_info.get("lastUpdate", ""))
            tags.append(f"#{MONTH_TAGS[last_update.month - 1]}{last_update.year}")
        except (ValueError, OverflowError, TypeError) as e:
            self.logger.debug(f"Не удалось получить дату для хэштега: {e}")

        return " ".join(tags)


class FullUpdateFormatter(UpdateMessageFormatter):
    """
    Полный формат: название, версия, время, описание изменений и хэштеги.
    Наследники задают только заголовок.
    """

    TITLE = ""

    def format(self, fnsi_info: dict, nsi_oid: Optional[str] = None) -> str:
        """
        Форматирует обновление с полной информацией.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника (для хэштегов)
        """
        try:
            nsi_oid = nsi_oid or fnsi_info.get("id", "")
            date_str = parser.parse(fnsi_info["lastUpdate"]).strftime("%H:%M %d.%m.%Y")
            hashtags = self.get_hashtags(fnsi_info, nsi_oid)
            release_notes = escape(format_releaseNotes(fnsi_info["releaseNotes"]))

            message = (
                f"{self.TITLE}\n\n"
                f"📋 <b>{escape(str(fnsi_info['shortName']))}</b>\n"
                f"ID: <code>{escape(str(fnsi_info['id']))}</code>\n"
                f"Версия: <code>{escape(str(fnsi_info['version']))}</code>\n"
                f"Время: {date_str}\n"
                f"\n💡 <i>Описание изменений:</i>\n"
                f"<i>{release_notes}</i>\n"
                f"\n🔗 <a href='{escape(passport_url(fnsi_info))}'>"
                f"Перейти к справочнику</a>"
            )

            if hashtags:
                message += f"\n\n{hashtags}"

            return message
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании обновления: {e}")
            return (
                f"{self.TITLE}\n"
                f"Справочник: <b>{escape(str(fnsi_info.get('shortName', 'Unknown')))}</b>\n"
                f"Версия: <code>{escape(str(fnsi_info.get('version', 'Unknown')))}</code>\n"
            )


class ImportantUpdateFormatter(FullUpdateFormatter):
    """Важные обновления: справочники, влияющие на критичные системы."""

    TITLE = "⚠️ <b>Важное обновление</b>"


class DefaultUpdateFormatter(FullUpdateFormatter):
    """Обычные обновления справочников."""

    TITLE = "🔄 <b>Обновление справочника</b>"


class MinorUpdateFormatter(UpdateMessageFormatter):
    """
    Укороченный формат для часто обновляемых справочников.
    """

    def format(self, fnsi_info: dict, nsi_oid: Optional[str] = None) -> str:
        """
        Форматирует обновление в укороченном виде.

        Args:
            fnsi_info: информация о справочнике
            nsi_oid: OID справочника (не используется)
        """
        try:
            return (
                f"📝 <b>{escape(str(fnsi_info['shortName']))}</b> "
                f"v{escape(str(fnsi_info['version']))}\n"
                f"   <a href='{escape(passport_url(fnsi_info))}'>"
                f"↗ {escape(str(fnsi_info['id']))}</a>"
            )
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании обновления: {e}")
            return (
                f"📝 <b>{escape(str(fnsi_info.get('shortName', 'Unknown')))}</b> "
                f"v{escape(str(fnsi_info.get('version', 'Unknown')))}"
            )

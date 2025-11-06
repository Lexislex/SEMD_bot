from datetime import date
from typing import List, NamedTuple
import logging
import html
import re


class SEMDRegistrationFormatter:
    """Форматирует сообщения о регистрации СЭМД"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def format_monthly(self, registrations: List, terminations: List, year: int, month: int) -> str:
        """
        Форматирует месячную сводку

        Args:
            registrations: Список DateGroup объектов с регистрациями
            terminations: Список DateGroup объектов с завершениями
            year: Год
            month: Месяц

        Returns:
            HTML-отформатированное сообщение
        """
        try:
            month_names = {
                1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель',
                5: 'май', 6: 'июнь', 7: 'июль', 8: 'август',
                9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь'
            }

            month_name = month_names.get(month, str(month))

            lines = []
            lines.append(f"📋 <b>СЭМД - Ежемесячная сводка за {month_name} {year}</b>")
            lines.append("")

            # Регистрации
            if registrations:
                lines.append("🟢 <b>Начинают регистрацию в РЭМД:</b>")
                for date_group in registrations:
                    lines.append(self._format_date_group(date_group))
                lines.append("")

            # Завершения
            if terminations:
                lines.append("🔴 <b>Прекращают регистрацию в РЭМД:</b>")
                for date_group in terminations:
                    lines.append(self._format_date_group(date_group))

            return "\n".join(lines)
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании месячной сводки: {e}")
            return "Ошибка при формировании сообщения"

    def format_quarterly(self, registrations: List, terminations: List, year: int, quarter: int) -> str:
        """
        Форматирует квартальную сводку

        Args:
            registrations: Список DateGroup объектов с регистрациями
            terminations: Список DateGroup объектов с завершениями
            year: Год
            quarter: Квартал (1-4)

        Returns:
            HTML-отформатированное сообщение
        """
        try:
            quarter_names = {
                1: 'I квартал',
                2: 'II квартал',
                3: 'III квартал',
                4: 'IV квартал'
            }

            quarter_name = quarter_names.get(quarter, f"{quarter} квартал")

            lines = []
            lines.append(f"📋 <b>СЭМД - Ежеквартальная сводка за {quarter_name} {year}</b>")
            lines.append("")

            # Регистрации
            if registrations:
                lines.append("🟢 <b>Начинают регистрацию в РЭМД:</b>")
                for date_group in registrations:
                    lines.append(self._format_date_group(date_group))
                lines.append("")

            # Завершения
            if terminations:
                lines.append("🔴 <b>Прекращают регистрацию в РЭМД:</b>")
                for date_group in terminations:
                    lines.append(self._format_date_group(date_group))

            return "\n".join(lines)
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании квартальной сводки: {e}")
            return "Ошибка при формировании сообщения"

    def _format_date_group(self, date_group) -> str:
        """
        Форматирует группу СЭМД на одну дату

        Args:
            date_group: DateGroup объект с датой и списком СЭМД

        Returns:
            Отформатированная строка:
            📅 01.01.2025
            • 119 Протокол консультации ред. 4
            • 134 Предоперационный эпикриз ред. 1
        """
        try:
            lines = []

            # Форматируем дату: DD.MM.YYYY
            date_str = date_group.date.strftime('%d.%m.%Y')
            lines.append(f"📅 {date_str}")

            # Выводим каждую СЭМД
            for semd_number, name in date_group.semds:
                # Экранируем HTML спецсимволы в наименовании
                safe_name = html.escape(name)
                # Убираем "(CDA)" и заменяем "Редакция" на "ред."
                safe_name = safe_name.replace(' (CDA)', '')

                # Проверяем есть ли "Редакция" в названии
                has_revision = 'Редакция' in safe_name
                revision_part = ''

                if has_revision:
                    # Извлекаем "Редакция X"
                    match = re.search(r'Редакция\s+(\S+)', safe_name)
                    if match:
                        revision_part = f' ред. {match.group(1)}'
                        # Удаляем "Редакция X" из названия
                        safe_name = safe_name[:match.start()].strip()

                # Сокращаем NAME: если больше 53 символов, берем первые 50 и добавляем "..."
                if len(safe_name) > 53:
                    safe_name = safe_name[:50] + '...' + revision_part
                else:
                    safe_name = safe_name + revision_part

                lines.append(f"• <u>{semd_number}</u> {safe_name}")

            return "\n".join(lines)
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании группы по датам: {e}")
            return ""

    def should_send_silent(self) -> bool:
        """
        Определяет, отправлять ли сообщение без звука
        Возвращает False - отправляем со звуком (как в NSI Update Checker)
        """
        return False

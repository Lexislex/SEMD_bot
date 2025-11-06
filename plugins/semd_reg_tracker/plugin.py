from typing import List, Dict, Any
from plugins.base import BasePlugin
from .handlers import SEMDRegistrationHandlers
import logging
from datetime import datetime


class Plugin(BasePlugin):
    """Плагин для отслеживания регистрации СЭМД в РЭМД"""

    # Plugin metadata
    access_level = "all"
    display_name = "📊 Отслеживание СЭМД"
    description = "Уведомления о начале/окончании регистрации СЭМД в РЭМД"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.handlers = SEMDRegistrationHandlers(bot, config)
        self.logger = logging.getLogger(__name__)

    def get_name(self) -> str:
        return "SEMDRegTracker"

    def get_version(self) -> str:
        return "1.0.0"

    def initialize(self) -> bool:
        """Инициализация плагина"""
        try:
            self.logger.info("Инициализация SEMDRegTracker")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка инициализации SEMDRegTracker: {e}")
            return False

    def get_commands(self) -> List[Dict[str, Any]]:
        """Регистрирует команды"""
        return []

    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Регистрирует callback-функции"""
        return []

    def get_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """
        Возвращает две задачи:
        1. Ежемесячная проверка (1 мин в dev, 1 месяц в prod)
        2. Ежеквартальная проверка (3 мин в dev, 1 квартал в prod)
        """
        is_dev = self.config.app.env == 'development'

        tasks = [
            {
                'func': self.check_monthly_updates,
                'interval': 1 if is_dev else 1,
                'unit': 'minutes' if is_dev else 'months',
                'at': '10:00',  # Время выполнения
                'task_name': 'monthly_semd_check'
            },
            {
                'func': self.check_quarterly_updates,
                'interval': 3 if is_dev else 1,
                'unit': 'minutes' if is_dev else 'quarters',
                'at': '10:00',  # Время выполнения
                'task_name': 'quarterly_semd_check'
            }
        ]

        return tasks

    def check_monthly_updates(self):
        """
        Проверяет и отправляет месячную сводку СЭМД
        В production: выполняется 1 числа каждого месяца в 10:00
        В development: выполняется каждую минуту

        Логика:
        - Если сегодня 1 число и это начало квартала -> пропускаем (отправит квартальная задача)
        - Иначе отправляем месячную сводку
        """
        try:
            now = datetime.now()

            # Проверяем, является ли текущая дата первым числом квартала
            is_quarter_start = now.day == 1 and now.month in [1, 4, 7, 10]

            # В production режиме проверяем день месяца
            if self.config.app.env == 'production':
                if now.day != 1:  # Выполняем только 1 числа месяца
                    return
                if is_quarter_start:  # Приоритет квартальной сводке
                    self.logger.info(
                        "Пропускаем месячную проверку - это начало квартала"
                    )
                    return

            # Отправляем месячную сводку
            self.logger.info("Начало проверки месячных обновлений СЭМД")
            success = self.handlers.send_monthly_update()

            if success:
                self.logger.info("Месячная сводка успешно отправлена")
            else:
                self.logger.warning("Не удалось отправить месячную сводку")

        except Exception as e:
            self.logger.error(f"Ошибка при проверке месячных обновлений: {e}")

    def check_quarterly_updates(self):
        """
        Проверяет и отправляет квартальную сводку СЭМД
        В production: выполняется 1 числа каждого квартала (1.01, 1.04, 1.07, 1.10) в 10:00
        В development: выполняется каждые 3 минуты

        Логика:
        - Если сегодня 1 число и это начало квартала -> отправляем квартальную сводку
        """
        try:
            now = datetime.now()

            # Проверяем, является ли текущая дата первым числом квартала
            is_quarter_start = now.day == 1 and now.month in [1, 4, 7, 10]

            # В production режиме проверяем день и месяц
            if self.config.app.env == 'production':
                if not is_quarter_start:  # Выполняем только 1 числа квартала
                    return

            # Отправляем квартальную сводку
            self.logger.info("Начало проверки квартальных обновлений СЭМД")
            success = self.handlers.send_quarterly_update()

            if success:
                self.logger.info("Квартальная сводка успешно отправлена")
            else:
                self.logger.warning("Не удалось отправить квартальную сводку")

        except Exception as e:
            self.logger.error(f"Ошибка при проверке квартальных обновлений: {e}")

    def shutdown(self):
        """Завершение работы плагина"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")

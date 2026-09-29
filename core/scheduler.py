import functools
import logging
import time
from datetime import datetime
from typing import Callable, Optional

import schedule


class TaskScheduler:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.tasks = {}

    def _safe(self, func: Callable, task_id: str) -> Callable:
        """Wrap a task so an exception is logged instead of killing the scheduler.

        ``schedule.run_pending()`` propagates exceptions from jobs; the scheduler
        runs in a daemon thread, so one failure would silently stop every task.
        """

        @functools.wraps(func)
        def wrapper():
            try:
                return func()
            except Exception as e:
                self.logger.exception(f"Ошибка при выполнении задачи {task_id}: {e}")

        return wrapper

    def add_task(
        self,
        func,
        interval: int,
        unit: str,
        at: Optional[str] = None,
        task_name: Optional[str] = None,
    ):
        """
        Добавляет задачу в планировщик

        Args:
            func: Функция для выполнения
            interval: Интервал выполнения
            unit: Единица времени ('minutes', 'seconds', 'hours', 'days', 'months', 'quarters')
            at: Время выполнения в формате "HH:MM" (опционально, для days/months/quarters)
            task_name: Имя задачи для идентификации (опционально)
        """
        task_id = task_name or func.__name__

        try:
            if unit == "minutes":
                job = schedule.every(interval).minutes
            elif unit == "seconds":
                job = schedule.every(interval).seconds
            elif unit == "hours":
                job = schedule.every(interval).hours
            elif unit == "days":
                job = schedule.every(interval).days
            elif unit in ("months", "quarters"):
                # schedule не поддерживает месяцы/кварталы: запускаем ежедневно,
                # нужный день проверяет сама задача
                job = schedule.every().day
            else:
                self.logger.error(f"Неизвестная единица времени: {unit}")
                return

            # at() до do(): иначе первый запуск считается от момента старта,
            # а не от указанного времени
            if at and unit in ("days", "months", "quarters"):
                job = job.at(at)
            job.do(self._safe(func, task_id)).tag(task_id)

            self.tasks[task_id] = func

            if unit == "months":
                log_msg = f"Задача {task_id} добавлена: ежемесячно (проверка ежедневно)"
            elif unit == "quarters":
                log_msg = (
                    f"Задача {task_id} добавлена: ежеквартально (проверка ежедневно)"
                )
            else:
                log_msg = f"Задача {task_id} добавлена: каждые {interval} {unit}"
            if at and unit in ("days", "months", "quarters"):
                log_msg += f" в {at}"
            self.logger.info(log_msg)

        except Exception as e:
            self.logger.error(f"Ошибка при добавлении задачи {task_id}: {e}")

    def start(self):
        """Запускает планировщик"""
        self.running = True
        self.logger.info("TaskScheduler запущен")

        while self.running:
            schedule.run_pending()  # Выполняет func() если пришло время
            time.sleep(1)

    def stop(self):
        """Останавливает планировщик"""
        self.running = False
        self.logger.info("TaskScheduler остановлен")

    def remove_task(self, task_id: str):
        """Удаляет задачу"""
        if task_id in self.tasks:
            schedule.clear(task_id)
            del self.tasks[task_id]

    @staticmethod
    def is_first_of_month() -> bool:
        """Проверяет, является ли текущая дата первым числом месяца"""
        return datetime.now().day == 1

    @staticmethod
    def is_first_of_quarter() -> bool:
        """
        Проверяет, является ли текущая дата первым числом квартала
        Квартальные даты: 1.01, 1.04, 1.07, 1.10
        """
        now = datetime.now()
        return now.day == 1 and now.month in [1, 4, 7, 10]

    @staticmethod
    def get_current_quarter() -> int:
        """Возвращает текущий квартал (1-4)"""
        now = datetime.now()
        return (now.month - 1) // 3 + 1

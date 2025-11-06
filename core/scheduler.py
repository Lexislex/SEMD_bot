import schedule
import time
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime


class TaskScheduler:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.tasks = {}
    
    def add_task(self, func, interval: int, unit: str, at: Optional[str] = None, task_name: Optional[str] = None):
        """
        Добавляет задачу в планировщик

        Args:
            func: Функция для выполнения
            interval: Интервал выполнения
            unit: Единица времени ('minutes', 'seconds', 'hours', 'days', 'months', 'quarters')
            at: Время выполнения в формате "HH:MM" (опционально)
            task_name: Имя задачи для идентификации (опционально)
        """
        task_id = task_name or func.__name__

        try:
            # Регистрируем в schedule библиотеке
            if unit == 'minutes':
                job = schedule.every(interval).minutes.do(func)
            elif unit == 'seconds':
                job = schedule.every(interval).seconds.do(func)
            elif unit == 'hours':
                job = schedule.every(interval).hours.do(func)
            elif unit == 'days':
                job = schedule.every(interval).days.do(func)
                # Поддержка параметра at для дневного расписания
                if at:
                    job.at(at)
            elif unit == 'months':
                # Для месячного расписания используем кастомную логику
                # schedule не поддерживает месячные интервалы, поэтому используем дневной интервал
                # с проверкой внутри функции
                job = schedule.every().day.do(func)
                if at:
                    job.at(at)
                self.logger.info(f"Задача {task_id} добавлена: ежемесячно в {at or 'любое время'} (проверка через день)")
            elif unit == 'quarters':
                # Для квартального расписания используем кастомную логику
                # schedule не поддерживает квартальные интервалы, поэтому используем дневной интервал
                # с проверкой внутри функции
                job = schedule.every().day.do(func)
                if at:
                    job.at(at)
                self.logger.info(f"Задача {task_id} добавлена: ежеквартально в {at or 'любое время'} (проверка через день)")
            else:
                self.logger.error(f"Неизвестная единица времени: {unit}")
                return

            self.tasks[task_id] = func

            # Логирование
            if unit not in ['months', 'quarters']:
                log_msg = f"Задача {task_id} добавлена: каждые {interval} {unit}"
                if at and unit in ['days', 'hours']:
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
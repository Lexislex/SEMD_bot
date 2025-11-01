import schedule
import time
from typing import Dict, List, Any
import logging

class TaskScheduler:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.tasks = {}
    
    def add_task(self, func, interval: int, unit: str):
        """Добавляет задачу в планировщик"""
        # func - это self.check_updates (из плагина)
        # interval - интервал (15)
        # unit - единица ('minutes', 'seconds', 'hours')
        
        task_id = func.__name__
        
        # Регистрируем в schedule библиотеке
        if unit == 'minutes':
            schedule.every(interval).minutes.do(func)
        elif unit == 'seconds':
            schedule.every(interval).seconds.do(func)
        elif unit == 'hours':
            schedule.every(interval).hours.do(func)
        
        self.tasks[task_id] = func
        self.logger.info(f"Задача {task_id} добавлена: каждые {interval} {unit}")
    
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
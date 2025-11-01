from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from telebot import TeleBot
from config import Config

class BasePlugin(ABC):
    """Базовый класс для всех плагинов"""
    
    def __init__(self, bot: TeleBot, config: Config):
        self.bot = bot
        self.config = config
        self.name = self.__class__.__name__
        
    @abstractmethod
    def get_name(self) -> str:
        """Возвращает имя плагина"""
        pass
        
    @abstractmethod
    def get_version(self) -> str:
        """Возвращает версию плагина"""
        pass
        
    @abstractmethod
    def initialize(self) -> bool:
        """Инициализация плагина"""
        pass
        
    def get_commands(self) -> List[Dict[str, Any]]:
        """Возвращает список команд, которые обрабатывает плагин"""
        return []
        
    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Возвращает список callback-функций"""
        return []
        
    def get_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """Возвращает список задач для планировщика"""
        return []
        
    def shutdown(self):
        """Завершение работы плагина"""
        pass

class ScheduledPlugin(BasePlugin):
    """Плагин с поддержкой планировщика"""
    
    @abstractmethod
    def get_schedule_config(self) -> Dict[str, Any]:
        """Конфигурация расписания"""
        pass
    
    def get_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """Использует get_schedule_config для создания задачи"""
        config = self.get_schedule_config()
        
        return [
            {
                'func': self.check_updates,  # Главная функция для выполнения
                'interval': config['interval'],
                'unit': config['unit']
            }
        ]
    
    @abstractmethod
    def check_updates(self):
        """Метод, который будет выполняться по расписанию"""
        pass
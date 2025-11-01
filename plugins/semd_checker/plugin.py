import logging
from typing import List, Dict, Any
from plugins.base import BasePlugin
from .handlers import SEMDHandlers

class Plugin(BasePlugin):
    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.logger = logging.getLogger(__name__)
        self.handlers = SEMDHandlers(bot, config)
        
    def get_name(self) -> str:
        return "SEMD_Checker"
        
    def get_version(self) -> str:
        return "1.0.0"
        
    def initialize(self) -> bool:
        try:
            # Инициализация данных СЭМД
            self.handlers.initialize_data()
            return True
        except Exception as e:
            self.logger.error(f"Ошибка инициализации SEMD_Checker: {e}")
            return False
            
    def get_commands(self) -> List[Dict[str, Any]]:
        return [
            {
                'params': {'commands': ['start', 'about']},
                'handler': self.handlers.start_handler
            }
        ]
        
    def get_callbacks(self) -> List[Dict[str, Any]]:
        return [
            {
                'params': {'func': lambda call: call.data == 'versions'},
                'handler': self.handlers.versions_callback
            }
        ]
from typing import List, Dict, Any
from plugins.base import ScheduledPlugin
from .handlers import NSIUpdHandlers
import logging

class Plugin(ScheduledPlugin):
    # Plugin metadata
    access_level = "all"
    display_name = "📋 Обновления НСИ"
    description = "Мониторинг обновлений справочников НСИ и информация о канале уведомлений"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.handlers = NSIUpdHandlers(bot, config)
        self.logger = logging.getLogger(__name__)

    def get_name(self) -> str:
        return "NSI_Update_Checker"

    def get_version(self) -> str:
        return "1.0.0"
    
    def initialize(self) -> bool:
        try:
            # Инициализация
            return True
        except Exception as e:
            self.logger.error(f"Ошибка инициализации NSI_Update_Checker: {e}")
            return False

    def get_commands(self) -> List[Dict[str, Any]]:
        """Register commands"""
        return []

    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Register callback handlers"""
        return [
            {
                'params': {'func': lambda call: call.data == "plugin_NSI_Update_Checker"},
                'handler': self.handlers.handle_nsi_checker_menu
            }
        ]

    def get_schedule_config(self) -> dict:
        """Конфигурация интервала проверки обновлений НСИ
        Development: каждую минуту
        Production: каждые 15 минут
        """
        # Конфигурация расписания
        if self.config.app.env == 'development':
            return {'interval': 1, 'unit': 'minutes'}
        else:
            return {'interval': 15, 'unit': 'minutes'}
    
    def check_updates(self):
        """Проверяет обновления НСИ справочников
        Вызывается по расписанию и уведомляет пользователей об обновлениях
        """
        # Вызывает handlers.check_updates()
        self.handlers.check_updates()

    def shutdown(self):
        """Shutdown plugin"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")
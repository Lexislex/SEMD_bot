import logging
from typing import Any, Dict, List

from plugins.base import ScheduledPlugin


class Plugin(ScheduledPlugin):
    # Plugin metadata
    access_level = "all"
    display_name = "🧩 Схематроны СЭМД"
    description = "Мониторинг изменений схематронов СЭМД в GitLab Минздрава"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.handlers = None
        self.logger = logging.getLogger(__name__)

    def get_name(self) -> str:
        return "Schematron_Monitor"

    def get_version(self) -> str:
        return "1.0.0"

    def initialize(self) -> bool:
        if not self.config.gitlab.token:
            self.logger.warning(
                "GITLAB_TOKEN не задан — мониторинг схематронов отключён"
            )
            return False
        try:
            from .handlers import SchematronHandlers

            self.handlers = SchematronHandlers(self.bot, self.config)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка инициализации Schematron_Monitor: {e}")
            return False

    def get_commands(self) -> List[Dict[str, Any]]:
        """Register commands"""
        return []

    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Register callback handlers"""
        return [
            {
                "params": {
                    "func": lambda call: call.data == "plugin_Schematron_Monitor"
                },
                "handler": self.handlers.handle_menu,
            }
        ]

    def get_schedule_config(self) -> dict:
        """Конфигурация интервала проверки схематронов
        Development: каждую минуту
        Production: каждые 60 минут
        """
        if self.config.app.env == "development":
            return {"interval": 1, "unit": "minutes"}
        else:
            return {"interval": 60, "unit": "minutes"}

    def check_updates(self):
        """Проверяет изменения схематронов и уведомляет подписчиков"""
        self.handlers.check_updates()

    def shutdown(self):
        """Shutdown plugin"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")

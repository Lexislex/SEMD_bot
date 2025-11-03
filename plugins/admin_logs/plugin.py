"""Admin Logs Plugin - System logs and monitoring"""
import logging
from typing import List, Dict, Any
from plugins.base import BasePlugin
from .handlers import AdminLogsHandlers


class Plugin(BasePlugin):
    """Admin Logs Plugin for viewing system logs"""

    # Plugin metadata
    access_level = "admin"
    display_name = "📋 Логи системы"
    description = "Просмотр логов активности пользователей"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.logger = logging.getLogger(__name__)
        self.handlers = AdminLogsHandlers(bot, config)

    def get_name(self) -> str:
        """Get plugin name"""
        return "AdminLogs"

    def get_version(self) -> str:
        """Get plugin version"""
        return "1.0.0"

    def initialize(self) -> bool:
        """Initialize the plugin"""
        try:
            self.logger.info(f"Plugin {self.get_name()} initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error initializing {self.get_name()}: {e}")
            return False

    def get_commands(self) -> List[Dict[str, Any]]:
        """Register commands"""
        return [
            {
                'params': {'commands': ['logs']},
                'handler': self.handlers.handle_logs
            }
        ]

    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Register callback handlers"""
        return [
            {
                'params': {'func': lambda call: call.data == "plugin_AdminLogs"},
                'handler': self.handlers.handle_logs_menu
            }
        ]

    def shutdown(self):
        """Shutdown plugin"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")

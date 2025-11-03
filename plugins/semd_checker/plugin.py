"""SEMD Checker Plugin - Search for SEMD document versions"""
import logging
from typing import List, Dict, Any
from plugins.base import BasePlugin
from .handlers import SEMDHandlers


class Plugin(BasePlugin):
    """SEMD Checker Plugin for searching document versions"""

    # Plugin metadata
    access_level = "all"
    display_name = "🔍 Поиск версий СЭМД"
    description = "Поиск информации о версиях структурированных электронных медицинских документов"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.logger = logging.getLogger(__name__)
        self.handlers = SEMDHandlers(bot, config)

    def get_name(self) -> str:
        """Get plugin name"""
        return "SEMDChecker"

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
                'params': {'commands': ['about']},
                'handler': self.handlers.handle_semd_about
            },
            {
                'params': {'content_types': ['text']},
                'handler': self.handlers.handle_semd_search
            }
        ]

    def get_callbacks(self) -> List[Dict[str, Any]]:
        """Register callback handlers"""
        return [
            {
                'params': {'func': lambda call: call.data == "plugin_SEMDChecker"},
                'handler': self.handlers.handle_semd_menu
            }
        ]

    def shutdown(self):
        """Shutdown plugin"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")
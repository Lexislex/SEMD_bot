"""Plugin Manager Plugin - Manage loaded plugins"""
import logging
from typing import List, Dict, Any
from plugins.base import BasePlugin
from .handlers import PluginManagerHandlers


class Plugin(BasePlugin):
    """Plugin Manager Plugin for managing plugins"""

    # Plugin metadata
    access_level = "admin"
    display_name = "🔌 Управление плагинами"
    description = "Просмотр списка загруженных плагинов и их статуса"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.logger = logging.getLogger(__name__)
        self.handlers = None
        self.plugin_manager = None

    def set_plugin_manager(self, plugin_manager):
        """Set reference to plugin manager"""
        self.plugin_manager = plugin_manager
        if self.handlers:
            self.handlers.plugin_manager = plugin_manager

    def get_name(self) -> str:
        """Get plugin name"""
        return "PluginManager"

    def get_version(self) -> str:
        """Get plugin version"""
        return "1.0.0"

    def initialize(self) -> bool:
        """Initialize the plugin"""
        try:
            # Handlers will be created when plugin_manager is set
            self.logger.info(f"Plugin {self.get_name()} initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error initializing {self.get_name()}: {e}")
            return False

    def set_plugin_manager(self, plugin_manager):
        """Set reference to plugin manager"""
        self.plugin_manager = plugin_manager
        # Create handlers now that we have plugin_manager
        if self.handlers is None:
            self.handlers = PluginManagerHandlers(self.bot, self.config, self.plugin_manager)

    def get_commands(self) -> List[Dict[str, Any]]:
        """Register commands"""
        if self.handlers is None:
            return []
        return [
            {
                'params': {'commands': ['plugins']},
                'handler': self.handlers.handle_plugins
            }
        ]

    def shutdown(self):
        """Shutdown plugin"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")

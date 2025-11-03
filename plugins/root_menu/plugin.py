"""Root Menu Plugin - Central routing hub"""
import logging
from plugins.base import BasePlugin
from .handlers import RootMenuHandlers


class Plugin(BasePlugin):
    """Root Menu Plugin for central routing"""

    # Plugin metadata
    access_level = "all"
    display_name = "📋 Главное меню"
    description = "Главное меню и маршрутизация между плагинами"

    def __init__(self, bot, config):
        super().__init__(bot, config)
        self.handlers = None
        self.plugin_manager = None
        self.logger = logging.getLogger(__name__)

    def set_plugin_manager(self, plugin_manager):
        """Set reference to plugin manager for accessing other plugins"""
        self.plugin_manager = plugin_manager

    def get_name(self) -> str:
        """Get plugin name"""
        return "RootMenu"

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
            self.logger.error(f"Error initializing RootMenu plugin: {e}")
            return False

    def set_plugin_manager(self, plugin_manager):
        """Set reference to plugin manager for accessing other plugins"""
        self.plugin_manager = plugin_manager
        # Create handlers now that we have plugin_manager
        if self.handlers is None:
            self.handlers = RootMenuHandlers(self.bot, self.config, self.plugin_manager)

    def get_commands(self):
        """Register commands"""
        if self.handlers is None:
            return []
        return [
            {
                'params': {'commands': ['start']},
                'handler': self.handlers.handle_start
            }
        ]

    def get_callbacks(self):
        """Register callback handlers"""
        if self.handlers is None:
            return []
        return [
            {
                'params': {'func': lambda call: call.data == "back_to_menu"},
                'handler': self.handlers.handle_back_button
            }
        ]

    def shutdown(self):
        """Shutdown plugin"""
        self.logger.info(f"Plugin {self.get_name()} shutting down")

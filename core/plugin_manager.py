from typing import List, Dict, Any
import importlib
import logging
from plugins.base import BasePlugin

class PluginManager:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.plugins: Dict[str, BasePlugin] = {}
        self.logger = logging.getLogger(__name__)
        
    def load_plugin(self, plugin_path: str) -> bool:
        """Загружает плагин по пути"""
        try:
            module = importlib.import_module(plugin_path)
            plugin_class = getattr(module, 'Plugin')
            plugin = plugin_class(self.bot, self.config)
            
            if plugin.initialize():
                self.plugins[plugin.get_name()] = plugin
                self._register_handlers(plugin)
                self.logger.info(f"Плагин {plugin.get_name()} загружен")
                return True
            else:
                self.logger.error(f"Ошибка инициализации плагина {plugin_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка загрузки плагина {plugin_path}: {e}")
            return False
            
    def _register_handlers(self, plugin: BasePlugin):
        """Регистрирует обработчики плагина в боте"""
        for command in plugin.get_commands():
            self.bot.message_handler(**command['params'])(command['handler'])
            
        for callback in plugin.get_callbacks():
            self.bot.callback_query_handler(**callback['params'])(callback['handler'])
            
    def get_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """Получает все задачи для планировщика"""
        tasks = []
        for plugin in self.plugins.values():
            tasks.extend(plugin.get_scheduled_tasks())
        return tasks

    def get_available_plugins(self, user_id: int) -> List[BasePlugin]:
        """
        Возвращает плагины, доступные для пользователя.

        Args:
            user_id: Telegram ID пользователя

        Returns:
            Список плагинов с доступом для пользователя
        """
        available = []
        for plugin in self.plugins.values():
            if plugin.has_access(user_id):
                available.append(plugin)
        return available

    def shutdown_all(self):
        """Завершает работу всех плагинов"""
        for plugin in self.plugins.values():
            plugin.shutdown()
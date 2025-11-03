import telebot
from threading import Thread
from core.plugin_manager import PluginManager
from core.scheduler import TaskScheduler

class SEMDBotCore:
    def __init__(self, config):
        self.config = config
        self.bot = telebot.TeleBot(config.app.bot_token)
        self.plugin_manager = PluginManager(self.bot, config)
        self.scheduler = TaskScheduler(config)
        
    def load_plugin(self, plugin_path: str) -> bool:
        result = self.plugin_manager.load_plugin(plugin_path)

        # Special handling for plugins that need plugin_manager reference
        if result:
            if "root_menu" in plugin_path:
                root_menu_plugin = self.plugin_manager.plugins.get("RootMenu")
                if root_menu_plugin:
                    root_menu_plugin.set_plugin_manager(self.plugin_manager)
            elif "plugin_manager" in plugin_path:
                plugin_mgr_plugin = self.plugin_manager.plugins.get("PluginManager")
                if plugin_mgr_plugin:
                    plugin_mgr_plugin.set_plugin_manager(self.plugin_manager)

        return result
        
    def start(self):
        # Запускаем планировщик в отдельном потоке
        tasks = self.plugin_manager.get_scheduled_tasks()
        for task in tasks:
            self.scheduler.add_task(**task)
            
        Thread(target=self.scheduler.start, daemon=True).start()
        
        # Запускаем бота
        self.bot.infinity_polling()
        
    def shutdown(self):
        self.plugin_manager.shutdown_all()
        self.scheduler.stop()
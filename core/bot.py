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
        return self.plugin_manager.load_plugin(plugin_path)
        
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
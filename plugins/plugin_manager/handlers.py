"""Plugin Manager plugin handlers"""
import logging
from telebot.types import Message

logger = logging.getLogger(__name__)


class PluginManagerHandlers:
    """Handlers for plugin manager plugin"""

    def __init__(self, bot, config, plugin_manager):
        self.bot = bot
        self.config = config
        self.plugin_manager = plugin_manager
        self.logger = logging.getLogger(__name__)

    def handle_plugins(self, message: Message):
        """Handle /plugins command - list all loaded plugins"""
        try:
            # Check admin access
            if message.from_user.id not in self.config.accounts.admin_ids:
                self.bot.send_message(
                    message.chat_id,
                    "❌ Доступ запрещен. Только для администраторов."
                )
                return

            # Get all plugins
            plugins = self.plugin_manager.plugins

            if not plugins:
                self.bot.send_message(
                    message.chat_id,
                    "📦 Нет загруженных плагинов."
                )
                return

            # Format plugin list
            plugins_text = "🔌 <b>Загруженные плагины:</b>\n\n"

            for name, plugin in plugins.items():
                version = plugin.get_version()
                access = plugin.access_level
                display_name = plugin.display_name or name
                status = "✅" if access == "admin" else "🔓"

                plugins_text += (
                    f"{status} <b>{display_name}</b>\n"
                    f"   Имя: {name}\n"
                    f"   Версия: {version}\n"
                    f"   Доступ: {access}\n"
                    f"   Описание: {plugin.description}\n\n"
                )

            self.bot.send_message(message.chat_id, plugins_text, parse_mode='html')

        except Exception as e:
            self.logger.error(f"Error in plugins handler: {e}")
            self.bot.send_message(
                message.chat_id,
                f"❌ Ошибка при получении списка плагинов: {e}"
            )

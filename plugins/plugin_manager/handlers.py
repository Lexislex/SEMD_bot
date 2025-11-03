"""Plugin Manager plugin handlers"""
import logging
from telebot.types import Message, CallbackQuery

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

    def handle_plugin_manager_menu(self, call: CallbackQuery):
        """Handle menu button click for Plugin Manager plugin"""
        try:
            # Check admin access
            if call.from_user.id not in self.config.accounts.admin_ids:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Доступ запрещен. Только для администраторов.",
                    show_alert=True
                )
                return

            menu_text = (
                "🔌 <b>Управление плагинами</b>\n\n"
                "<b>Функция:</b> Просмотр списка загруженных плагинов и их статуса\n\n"
                "<b>Доступные команды:</b>\n"
                "• /plugins - Показать список всех загруженных плагинов\n\n"
                "<b>Версия:</b> 1.0.0\n\n"
                "⚠️ <i>Только для администраторов</i>"
            )

            from .keyboards import get_back_button
            markup = get_back_button()

            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=menu_text,
                parse_mode='html',
                reply_markup=markup
            )
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            self.logger.error(f"Error in plugin manager menu handler: {e}")
            self.bot.answer_callback_query(call.id, "❌ Ошибка при обработке запроса", show_alert=True)

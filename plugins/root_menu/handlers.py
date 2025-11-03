"""Handlers for Root Menu plugin"""
import logging
from telebot import types
from .keyboards import get_main_menu_keyboard, get_back_button

logger = logging.getLogger(__name__)


class RootMenuHandlers:
    """Handlers for main menu and routing"""

    def __init__(self, bot, config, plugin_manager):
        self.bot = bot
        self.config = config
        self.plugin_manager = plugin_manager
        self.logger = logging.getLogger(__name__)

    def handle_start(self, message):
        """Handle /start command"""
        user_id = message.from_user.id
        welcome_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я помощник для мониторинга СЭМД и справочников НСИ.\n\n"
            "Выбери интересующую тебя функцию:"
        )

        available_plugins = self.plugin_manager.get_available_plugins(user_id)
        keyboard = get_main_menu_keyboard(available_plugins)

        self.bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)

    def handle_menu(self, message):
        """Handle /menu command"""
        user_id = message.from_user.id
        menu_text = "📋 Главное меню:\n\nВыбери функцию:"

        available_plugins = self.plugin_manager.get_available_plugins(user_id)
        keyboard = get_main_menu_keyboard(available_plugins)

        self.bot.send_message(message.chat.id, menu_text, reply_markup=keyboard)

    def handle_back_button(self, call):
        """Handle back to menu button"""
        user_id = call.from_user.id
        menu_text = "📋 Вернулись в главное меню.\n\nВыбери функцию:"

        available_plugins = self.plugin_manager.get_available_plugins(user_id)
        keyboard = get_main_menu_keyboard(available_plugins)

        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=menu_text,
            reply_markup=keyboard
        )
        self.bot.answer_callback_query(call.id)

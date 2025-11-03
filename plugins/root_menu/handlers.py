"""Handlers for Root Menu plugin"""
import logging
from telebot import types
from utils.message_manager import get_message_manager, cleanup_previous_message
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
        # Filter out RootMenu plugin from the menu
        available_plugins = [p for p in available_plugins if p.get_name() != "RootMenu"]
        keyboard = get_main_menu_keyboard(available_plugins)

        sent_msg = self.bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)
        # Track this message for later cleanup
        get_message_manager().update_message(message.chat.id, sent_msg.message_id, user_id)

    def handle_back_button(self, call):
        """Handle back to menu button"""
        user_id = call.from_user.id
        menu_text = "📋 Вернулись в главное меню.\n\nВыбери функцию:"

        available_plugins = self.plugin_manager.get_available_plugins(user_id)
        # Filter out RootMenu plugin from the menu
        available_plugins = [p for p in available_plugins if p.get_name() != "RootMenu"]
        keyboard = get_main_menu_keyboard(available_plugins)

        # Remove keyboard from previous message
        cleanup_previous_message(self.bot, call.message.chat.id)

        # Send menu as a new message instead of editing
        sent_msg = self.bot.send_message(
            chat_id=call.message.chat.id,
            text=menu_text,
            reply_markup=keyboard
        )
        # Update tracked message to current one
        get_message_manager().update_message(call.message.chat.id, sent_msg.message_id, user_id)
        self.bot.answer_callback_query(call.id)

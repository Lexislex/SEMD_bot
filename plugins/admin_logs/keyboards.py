"""Keyboards for Admin Logs plugin"""
from telebot import types


def get_back_button():
    """Get back to menu button"""
    button = types.InlineKeyboardButton(text="« Назад в меню", callback_data="back_to_menu")
    markup = types.InlineKeyboardMarkup()
    markup.add(button)
    return markup

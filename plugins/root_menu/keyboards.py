"""Keyboards for Root Menu plugin"""
from telebot import types


def get_main_menu_keyboard(available_plugins):
    """
    Generate main menu keyboard based on available plugins.

    Args:
        available_plugins: List of BasePlugin instances available to user

    Returns:
        InlineKeyboardMarkup with buttons for each plugin
    """
    markup = types.InlineKeyboardMarkup()

    for plugin in available_plugins:
        button_text = plugin.display_name or plugin.get_name()
        callback_data = f"plugin_{plugin.get_name()}"
        button = types.InlineKeyboardButton(text=button_text, callback_data=callback_data)
        markup.add(button)

    return markup


def get_back_button():
    """Get back to menu button"""
    button = types.InlineKeyboardButton(text="« Назад в меню", callback_data="back_to_menu")
    markup = types.InlineKeyboardMarkup()
    markup.add(button)
    return markup

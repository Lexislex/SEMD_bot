"""Keyboards for SEMD Checker plugin"""

from telebot import types


def get_back_button():
    """Get back to menu button"""
    button = types.InlineKeyboardButton(
        text="« Назад в меню", callback_data="back_to_menu"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(button)
    return markup


def get_search_results_keyboard(results: list):
    """
    Create keyboard with search results.

    Args:
        results: List of tuples [(TYPE, display_name), ...]

    Returns:
        InlineKeyboardMarkup with result buttons + back button
    """
    markup = types.InlineKeyboardMarkup()

    for doc_type, display_name in results:
        callback_data = f"semd_t:{doc_type}"
        button = types.InlineKeyboardButton(
            text=display_name, callback_data=callback_data
        )
        markup.add(button)

    # Add back button
    back_button = types.InlineKeyboardButton(
        text="« Назад в меню", callback_data="back_to_menu"
    )
    markup.add(back_button)

    return markup

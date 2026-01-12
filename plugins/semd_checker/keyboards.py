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


def get_search_results_keyboard(
    results: list,
    total_count: int = 0,
    current_offset: int = 0,
    page_size: int = 5,
):
    """
    Create keyboard with search results and pagination.

    Args:
        results: List of tuples [(TYPE, display_name), ...]
        total_count: Total number of results (for pagination)
        current_offset: Current offset (for pagination buttons)
        page_size: Number of results per page

    Returns:
        InlineKeyboardMarkup with result buttons + pagination + back button
    """
    markup = types.InlineKeyboardMarkup()

    for doc_type, display_name in results:
        callback_data = f"semd_t:{doc_type}"
        button = types.InlineKeyboardButton(
            text=display_name, callback_data=callback_data
        )
        markup.add(button)

    # Add pagination buttons if needed
    if total_count > page_size:
        pagination_buttons = []

        # Previous page button
        if current_offset > 0:
            prev_offset = max(0, current_offset - page_size)
            pagination_buttons.append(
                types.InlineKeyboardButton(
                    text="« Назад", callback_data=f"semd_p:{prev_offset}"
                )
            )

        # Page indicator
        current_page = (current_offset // page_size) + 1
        total_pages = (total_count + page_size - 1) // page_size
        pagination_buttons.append(
            types.InlineKeyboardButton(
                text=f"{current_page}/{total_pages}", callback_data="semd_noop"
            )
        )

        # Next page button
        if current_offset + page_size < total_count:
            next_offset = current_offset + page_size
            pagination_buttons.append(
                types.InlineKeyboardButton(
                    text="Вперёд »", callback_data=f"semd_p:{next_offset}"
                )
            )

        markup.add(*pagination_buttons)

    # Add back button
    back_button = types.InlineKeyboardButton(
        text="« Назад в меню", callback_data="back_to_menu"
    )
    markup.add(back_button)

    return markup

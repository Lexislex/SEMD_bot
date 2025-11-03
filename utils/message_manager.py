"""Message manager for handling button cleanup and message tracking"""
import logging
from typing import Dict, Tuple, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class MessageManager:
    """
    Manages message state to ensure buttons only appear on the latest message.

    Tracks the last message ID for each chat to ensure we remove buttons from
    previous messages when new ones are sent.
    """

    def __init__(self):
        self._chat_messages: Dict[int, Tuple[int, int]] = {}  # chat_id -> (message_id, user_id)
        self._lock = Lock()

    def update_message(self, chat_id: int, message_id: int, user_id: int) -> None:
        """
        Update the last message ID for a chat.

        Args:
            chat_id: Telegram chat ID
            message_id: Telegram message ID
            user_id: User ID who sent/received the message
        """
        with self._lock:
            self._chat_messages[chat_id] = (message_id, user_id)

    def get_last_message(self, chat_id: int) -> Optional[Tuple[int, int]]:
        """
        Get the last message ID for a chat.

        Returns:
            Tuple of (message_id, user_id) or None if no message tracked
        """
        with self._lock:
            return self._chat_messages.get(chat_id)

    def clear_message(self, chat_id: int) -> None:
        """Clear message tracking for a chat."""
        with self._lock:
            if chat_id in self._chat_messages:
                del self._chat_messages[chat_id]


# Global message manager instance
_message_manager = MessageManager()


def get_message_manager() -> MessageManager:
    """Get the global message manager instance."""
    return _message_manager


def remove_keyboard_from_message(bot, chat_id: int, message_id: int) -> bool:
    """
    Remove keyboard markup from a message.

    Args:
        bot: Telebot instance
        chat_id: Telegram chat ID
        message_id: Telegram message ID

    Returns:
        True if successful, False otherwise
    """
    try:
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None
        )
        logger.debug(f"Removed keyboard from message {message_id} in chat {chat_id}")
        return True
    except Exception as e:
        # Ignore error if message is not modified (keyboard wasn't there)
        error_str = str(e)
        if "message is not modified" in error_str or "not modified" in error_str:
            logger.debug(f"Message {message_id} had no keyboard to remove")
            return True
        logger.debug(f"Could not remove keyboard from message {message_id}: {e}")
        return False


def cleanup_previous_message(bot, chat_id: int) -> None:
    """
    Remove keyboard from the previous message in a chat.

    Args:
        bot: Telebot instance
        chat_id: Telegram chat ID
    """
    manager = get_message_manager()
    last_message = manager.get_last_message(chat_id)

    if last_message:
        message_id, _ = last_message
        remove_keyboard_from_message(bot, chat_id, message_id)

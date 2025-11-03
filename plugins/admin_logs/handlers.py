"""Admin Logs plugin handlers"""
import logging
from telebot.types import Message, CallbackQuery
from services.database_service import get_activity
from utils.message_manager import get_message_manager, cleanup_previous_message
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AdminLogsHandlers:
    """Handlers for admin logs plugin"""

    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)

    def handle_logs(self, message: Message):
        """Handle /logs command - show recent activity logs"""
        try:
            # Check admin access
            if message.from_user.id not in self.config.accounts.admin_ids:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Доступ запрещен. Только для администраторов."
                )
                return

            # Log the activity
            cleanup_previous_message(self.bot, message.chat.id)

            # Get last 7 days of logs
            stop_date = datetime.now().date()
            start_date = stop_date - timedelta(days=7)

            # Get activity data
            activity_data = get_activity(start_date, stop_date)

            if not activity_data:
                from .keyboards import get_back_button
                markup = get_back_button()
                sent_msg = self.bot.send_message(
                    message.chat.id,
                    "📋 Нет логов активности за последние 7 дней.",
                    reply_markup=markup
                )
                get_message_manager().update_message(message.chat.id, sent_msg.message_id, message.from_user.id)
                return

            # Format logs
            logs_text = "📋 <b>Недавние логи активности (последние 7 дней):</b>\n\n"

            # Show last 50 entries
            for entry in activity_data[-50:]:
                user_id, activity, date_time = entry
                logs_text += f"👤 {user_id} | {activity} | {date_time}\n"

            # Send in chunks if too long
            from .keyboards import get_back_button
            markup = get_back_button()
            if len(logs_text) > 4096:
                parts = [logs_text[i:i+4096] for i in range(0, len(logs_text), 4096)]
                last_msg = None
                for i, part in enumerate(parts):
                    # Add markup only to the last part
                    is_last = (i == len(parts) - 1)
                    last_msg = self.bot.send_message(
                        message.chat.id,
                        part,
                        parse_mode='html',
                        reply_markup=markup if is_last else None
                    )
                if last_msg:
                    get_message_manager().update_message(message.chat.id, last_msg.message_id, message.from_user.id)
            else:
                sent_msg = self.bot.send_message(message.chat.id, logs_text, parse_mode='html', reply_markup=markup)
                get_message_manager().update_message(message.chat.id, sent_msg.message_id, message.from_user.id)

        except Exception as e:
            self.logger.error(f"Error in logs handler: {e}")
            from .keyboards import get_back_button
            markup = get_back_button()
            sent_msg = self.bot.send_message(
                message.chat.id,
                f"❌ Ошибка при получении логов: {e}",
                reply_markup=markup
            )
            get_message_manager().update_message(message.chat.id, sent_msg.message_id, message.from_user.id)

    def handle_logs_menu(self, call: CallbackQuery):
        """Handle menu button click for Admin Logs plugin"""
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
                "📋 <b>Логи системы</b>\n\n"
                "<b>Функция:</b> Просмотр логов активности пользователей\n\n"
                "<b>Доступные команды:</b>\n"
                "• /logs - Показать логи за последние 7 дней\n\n"
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
            # Update tracked message to current one
            get_message_manager().update_message(call.message.chat.id, call.message.message_id, call.from_user.id)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            self.logger.error(f"Error in logs menu handler: {e}")
            self.bot.answer_callback_query(call.id, "❌ Ошибка при обработке запроса", show_alert=True)

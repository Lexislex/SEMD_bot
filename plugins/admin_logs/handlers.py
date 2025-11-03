"""Admin Logs plugin handlers"""
import logging
from telebot.types import Message
from services.database_service import get_activity
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

            # Get last 7 days of logs
            stop_date = datetime.now().date()
            start_date = stop_date - timedelta(days=7)

            # Get activity data
            activity_data = get_activity(start_date, stop_date)

            if not activity_data:
                self.bot.send_message(
                    message.chat.id,
                    "📋 Нет логов активности за последние 7 дней."
                )
                return

            # Format logs
            logs_text = "📋 <b>Недавние логи активности (последние 7 дней):</b>\n\n"

            # Show last 50 entries
            for entry in activity_data[-50:]:
                user_id, activity, date_time = entry
                logs_text += f"👤 {user_id} | {activity} | {date_time}\n"

            # Send in chunks if too long
            if len(logs_text) > 4096:
                parts = [logs_text[i:i+4096] for i in range(0, len(logs_text), 4096)]
                for part in parts:
                    self.bot.send_message(message.chat.id, part, parse_mode='html')
            else:
                self.bot.send_message(message.chat.id, logs_text, parse_mode='html')

        except Exception as e:
            self.logger.error(f"Error in logs handler: {e}")
            self.bot.send_message(
                message.chat.id,
                f"❌ Ошибка при получении логов: {e}"
            )

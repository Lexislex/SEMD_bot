"""Statistics plugin handlers"""
import datetime
import logging
import pandas as pd
from tabulate import tabulate
from telebot.types import Message
from utils.date_utils import next_weekday
from services.database_service import get_activity, add_log

logger = logging.getLogger(__name__)


class StatisticsHandlers:
    """Handlers for statistics plugin"""

    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)

    def handle_stat(self, message: Message):
        """Handle /stat command - show weekly statistics"""
        try:
            # Check admin access
            if message.from_user.id not in self.config.accounts.admin_ids:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Доступ запрещен. Только для администраторов."
                )
                return

            # Log the activity
            add_log(message)

            # Get statistics for last 3 weeks
            week = -3
            start_date = next_weekday(datetime.datetime.now().date(), 0, week)
            stop_date = start_date + datetime.timedelta(21)

            # Get activity data
            activity_data = get_activity(start_date, stop_date)

            if not activity_data:
                self.bot.send_message(
                    message.chat.id,
                    "📊 Нет данных активности за указанный период."
                )
                return

            # Process data
            df = pd.DataFrame(activity_data, columns=['user_id', 'activity', 'date_time'])
            df['date_time'] = pd.to_datetime(df['date_time'])

            # Exclude admin from statistics
            df = df[~df['user_id'].isin(self.config.accounts.admin_ids)]

            if df.empty:
                self.bot.send_message(
                    message.chat.id,
                    "📊 Нет данных активности от пользователей за указанный период."
                )
                return

            # Create pivot table
            df['week'] = df['date_time'].dt.isocalendar().week
            df = df.pivot_table(index=['activity'], columns='week', values='user_id', aggfunc='count')
            df.index.name = None
            df = df.fillna(0)

            # Format and send
            stats_text = (
                "📊 <b>Статистика активности по неделям:</b>\n\n"
                f"<pre>{tabulate(df, headers='keys', tablefmt='psql')}</pre>"
            )

            self.bot.send_message(message.chat.id, stats_text, parse_mode='html')

        except Exception as e:
            self.logger.error(f"Error in statistics handler: {e}")
            self.bot.send_message(
                message.chat.id,
                f"❌ Ошибка при получении статистики: {e}"
            )

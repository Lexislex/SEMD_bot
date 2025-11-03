"""Statistics plugin handlers"""
import datetime
import logging
import pandas as pd
from tabulate import tabulate
from telebot.types import Message, CallbackQuery
from utils.date_utils import next_weekday
from utils.message_manager import get_message_manager, cleanup_previous_message
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

            # Remove keyboard from previous message
            cleanup_previous_message(self.bot, message.chat.id)

            # Get statistics for last 3 weeks
            week = -3
            start_date = next_weekday(datetime.datetime.now().date(), 0, week)
            stop_date = start_date + datetime.timedelta(21)

            # Get activity data
            activity_data = get_activity(start_date, stop_date)

            if not activity_data:
                from .keyboards import get_back_button
                markup = get_back_button()
                sent_msg = self.bot.send_message(
                    message.chat.id,
                    "📊 Нет данных активности за указанный период.",
                    reply_markup=markup
                )
                get_message_manager().update_message(message.chat.id, sent_msg.message_id, message.from_user.id)
                return

            # Process data
            df = pd.DataFrame(activity_data, columns=['user_id', 'activity', 'date_time'])
            df['date_time'] = pd.to_datetime(df['date_time'])

            # Exclude admin from statistics
            df = df[~df['user_id'].isin(self.config.accounts.admin_ids)]

            if df.empty:
                from .keyboards import get_back_button
                markup = get_back_button()
                sent_msg = self.bot.send_message(
                    message.chat.id,
                    "📊 Нет данных активности от пользователей за указанный период.",
                    reply_markup=markup
                )
                get_message_manager().update_message(message.chat.id, sent_msg.message_id, message.from_user.id)
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

            sent_msg = self.bot.send_message(message.chat.id, stats_text, parse_mode='html')
            get_message_manager().update_message(message.chat.id, sent_msg.message_id, message.from_user.id)

        except Exception as e:
            self.logger.error(f"Error in statistics handler: {e}")
            from .keyboards import get_back_button
            markup = get_back_button()
            sent_msg = self.bot.send_message(
                message.chat.id,
                f"❌ Ошибка при получении статистики: {e}",
                reply_markup=markup
            )
            get_message_manager().update_message(message.chat.id, sent_msg.message_id, message.from_user.id)

    def handle_stat_menu(self, call: CallbackQuery):
        """Handle menu button click for Statistics plugin"""
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
                "📊 <b>Статистика</b>\n\n"
                "<b>Функция:</b> Просмотр статистики активности пользователей\n\n"
                "<b>Доступные команды:</b>\n"
                "• /stat - Показать статистику за последние 3 недели\n\n"
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
            self.logger.error(f"Error in statistics menu handler: {e}")
            self.bot.answer_callback_query(call.id, "❌ Ошибка при обработке запроса", show_alert=True)

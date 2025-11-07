import pandas as pd
from datetime import datetime, date
from typing import List, Tuple, Dict, Optional
from collections import namedtuple
import logging
from telebot.types import CallbackQuery
from utils.message_manager import get_message_manager, cleanup_previous_message

# Структура для группировки по датам
DateGroup = namedtuple('DateGroup', ['date', 'semds'])


class SEMDRegistrationHandlers:
    """Обработчик для отслеживания регистрации СЭМД"""

    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.semd1520 = None
        self.logger = logging.getLogger(__name__)
        self._load_semd_data()

    def _load_semd_data(self) -> bool:
        """
        Загружает справочник SEMD1520
        OID = '1.2.643.5.1.13.13.11.1520'
        Возвращает True если успешно, False если ошибка
        """
        try:
            from plugins.semd_checker.semd_logic import SEMD1520 #TODO сделать класс общим

            # Загружаем справочник SEMD1520 через существующий класс
            semd = SEMD1520()

            if semd.df is not None and not semd.df.empty:
                # Используем DataFrame из SEMD1520
                self.semd1520 = semd.df.copy()
                self.logger.info(f"Справочник SEMD1520 загружен: {len(self.semd1520)} записей")
                return True
            else:
                self.logger.warning("Справочник SEMD1520 пуст или не загружен")
                return False
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке справочника SEMD1520: {e}")
            return False

    def _get_monthly_registrations(self, year: int, month: int) -> pd.DataFrame:
        """Получает СЭМД, начинающие регистрацию в указанном месяце"""
        if self.semd1520 is None or self.semd1520.empty:
            return pd.DataFrame()

        try:
            df = self.semd1520
            # Фильтруем по START_DATE в указанном месяце и году
            monthly_data = df[
                (df['START_DATE'].dt.month == month) &
                (df['START_DATE'].dt.year == year)
            ].copy()

            return monthly_data
        except Exception as e:
            self.logger.error(f"Ошибка при фильтрации START_DATE: {e}")
            return pd.DataFrame()

    def _get_monthly_terminations(self, year: int, month: int) -> pd.DataFrame:
        """Получает СЭМД, прекращающие регистрацию в указанном месяце"""
        if self.semd1520 is None or self.semd1520.empty:
            return pd.DataFrame()

        try:
            df = self.semd1520
            # Фильтруем по END_DATE в указанном месяце и году
            monthly_data = df[
                (df['END_DATE'].dt.month == month) &
                (df['END_DATE'].dt.year == year)
            ].copy()

            return monthly_data
        except Exception as e:
            self.logger.error(f"Ошибка при фильтрации END_DATE: {e}")
            return pd.DataFrame()

    def _get_quarterly_registrations(self, year: int, quarter: int) -> pd.DataFrame:
        """Получает СЭМД, начинающие регистрацию в указанном квартале"""
        if self.semd1520 is None or self.semd1520.empty:
            return pd.DataFrame()

        try:
            # Определяем месяцы квартала
            q_months = {
                1: [1, 2, 3],
                2: [4, 5, 6],
                3: [7, 8, 9],
                4: [10, 11, 12]
            }

            months = q_months.get(quarter, [])
            df = self.semd1520

            quarterly_data = df[
                (df['START_DATE'].dt.month.isin(months)) &
                (df['START_DATE'].dt.year == year)
            ].copy()

            return quarterly_data
        except Exception as e:
            self.logger.error(f"Ошибка при фильтрации квартальных данных START_DATE: {e}")
            return pd.DataFrame()

    def _get_quarterly_terminations(self, year: int, quarter: int) -> pd.DataFrame:
        """Получает СЭМД, прекращающие регистрацию в указанном квартале"""
        if self.semd1520 is None or self.semd1520.empty:
            return pd.DataFrame()

        try:
            # Определяем месяцы квартала
            q_months = {
                1: [1, 2, 3],
                2: [4, 5, 6],
                3: [7, 8, 9],
                4: [10, 11, 12]
            }

            months = q_months.get(quarter, [])
            df = self.semd1520

            quarterly_data = df[
                (df['END_DATE'].dt.month.isin(months)) &
                (df['END_DATE'].dt.year == year)
            ].copy()

            return quarterly_data
        except Exception as e:
            self.logger.error(f"Ошибка при фильтрации квартальных данных END_DATE: {e}")
            return pd.DataFrame()

    def _group_by_date(self, df: pd.DataFrame, column: str = 'START_DATE') -> List[DateGroup]:
        """
        Группирует DataFrame по датам
        Возвращает список DateGroup объектов, где каждый содержит дату и список СЭМД

        Список СЭМД содержит кортежи (номер_сэмд, name), где:
        - номер_сэмд - последняя часть OID после последней точки
        - name - полное наименование из CSV
        """
        if df.empty:
            return []

        try:
            # Сортируем по датам
            df_sorted = df.sort_values(column)

            # Группируем по датам
            groups = []
            for date_value, group_df in df_sorted.groupby(df_sorted[column].dt.date):
                # Внутри группы сортируем по OID
                group_sorted = group_df.sort_values('OID')

                # Извлекаем номера СЭМД (последняя часть OID) и имена
                semds = []
                for _, row in group_sorted.iterrows():
                    oid = str(row['OID'])
                    name = str(row['NAME'])

                    # Берем последнюю часть OID после последней точки
                    semd_number = oid.split('.')[-1] if '.' in oid else oid

                    semds.append((semd_number, name))

                groups.append(DateGroup(date=date_value, semds=semds))

            return groups
        except Exception as e:
            self.logger.error(f"Ошибка при группировке по датам: {e}")
            return []

    def send_monthly_update(self) -> bool:
        """
        Отправляет месячную сводку по СЭМД
        Возвращает True если успешно отправлено, False иначе
        """
        try:
            now = datetime.now()
            year = now.year
            month = now.month

            # Перезагружаем данные перед проверкой
            if not self._load_semd_data():
                self.logger.warning("Невозможно отправить месячную сводку - справочник не загружен")
                return False

            # Получаем регистрации и завершения
            registrations = self._get_monthly_registrations(year, month)
            terminations = self._get_monthly_terminations(year, month)

            # Если нет ни регистраций, ни завершений - ничего не отправляем
            if registrations.empty and terminations.empty:
                self.logger.info(f"Нет СЭМД регистраций/завершений за {month}/{year}")
                return True

            # Форматируем сообщение
            from .formatters import SEMDRegistrationFormatter
            formatter = SEMDRegistrationFormatter()

            reg_groups = self._group_by_date(registrations, 'START_DATE')
            term_groups = self._group_by_date(terminations, 'END_DATE')

            message = formatter.format_monthly(reg_groups, term_groups, year, month)

            # Отправляем в рассылку
            return self._send_to_mailing_list(message)

        except Exception as e:
            self.logger.error(f"Ошибка при отправке месячной сводки: {e}")
            return False

    def send_quarterly_update(self) -> bool:
        """
        Отправляет квартальную сводку по СЭМД
        Возвращает True если успешно отправлено, False иначе
        """
        try:
            now = datetime.now()
            year = now.year
            month = now.month

            # Определяем квартал
            quarter = (month - 1) // 3 + 1

            # Перезагружаем данные перед проверкой
            if not self._load_semd_data():
                self.logger.warning("Невозможно отправить квартальную сводку - справочник не загружен")
                return False

            # Получаем регистрации и завершения
            registrations = self._get_quarterly_registrations(year, quarter)
            terminations = self._get_quarterly_terminations(year, quarter)

            # Если нет ни регистраций, ни завершений - ничего не отправляем
            if registrations.empty and terminations.empty:
                self.logger.info(f"Нет СЭМД регистраций/завершений за {quarter} квартал {year}")
                return True

            # Форматируем сообщение
            from .formatters import SEMDRegistrationFormatter
            formatter = SEMDRegistrationFormatter()

            reg_groups = self._group_by_date(registrations, 'START_DATE')
            term_groups = self._group_by_date(terminations, 'END_DATE')

            message = formatter.format_quarterly(reg_groups, term_groups, year, quarter)

            # Отправляем в рассылку
            return self._send_to_mailing_list(message)

        except Exception as e:
            self.logger.error(f"Ошибка при отправке квартальной сводки: {e}")
            return False

    def _send_to_mailing_list(self, message: str) -> bool:
        """
        Отправляет сообщение в список рассылки UPDS_MAILING_LIST
        """
        try:
            # Получаем список рассылки из конфига
            mailing_list = self.config.accounts.updates_mailing_list

            if not mailing_list:
                self.logger.warning("Список рассылки UPDS_MAILING_LIST пуст")
                return False

            success_count = 0
            for chat_id in mailing_list:
                try:
                    # Отправляем сообщение в каждый chat_id со звуком (disable_notification=False)
                    self.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML',
                        disable_notification=False
                    )
                    success_count += 1
                except Exception as e:
                    self.logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")

            if success_count > 0:
                self.logger.info(f"Сообщение отправлено в {success_count} чатов из {len(mailing_list)}")
                return True
            else:
                self.logger.warning("Не удалось отправить сообщение ни в один чат")
                return False

        except Exception as e:
            self.logger.error(f"Ошибка при отправке в рассылку: {e}")
            return False

    def handle_semd_reg_tracker_menu(self, call: CallbackQuery): #FIXME
        """
        Handle the SEMD Reg Tracker Update Checker menu button click.
        Shows information about where updates are posted.

        Args:
            call: CallbackQuery object from Telegram
        """
        try:
            info_text = (
                "📢 <b>Монитор регистрации СЭДМ в РЭМД</b>\n\n"
                "Информация о начале и окончании регистрации постятся в канал:\n"
                "<b>«СЭМД инфо»</b>\n\n"
                "🔗 Приглашение в канал:\n"
                "https://t.me/+QGan41q3n6U1MzJi\n\n"
                "Для получения уведомлений подпишитесь на канал!"
            )

            # Import here to avoid circular imports
            from .keyboards import get_back_button
            markup = get_back_button()

            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=info_text,
                parse_mode='html',
                reply_markup=markup
            )
            # Update tracked message to current one
            get_message_manager().update_message(call.message.chat.id, call.message.message_id, call.from_user.id)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            self.logger.error(f"Ошибка при обработке меню SEMD Reg Tracker: {e}")
            self.bot.answer_callback_query(call.id, "❌ Ошибка при обработке запроса", show_alert=True)
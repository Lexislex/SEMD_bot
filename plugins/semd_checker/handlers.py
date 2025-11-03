"""SEMD Checker plugin handlers"""
import logging
from telebot import types
from telebot.types import Message, CallbackQuery
from services.database_service import add_log
from .semd_logic import SEMD1520
from .keyboards import get_back_button

logger = logging.getLogger(__name__)


class SEMDHandlers:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.semd = SEMD1520()

    def handle_semd_search(self, message: Message):
        """Handle text messages - search for SEMD by OID or name"""
        try:
            # Ignore commands (they start with /)
            if message.text.startswith('/'):
                return

            # Log the activity
            add_log(message)

            search_text = message.text.strip()

            # Try to parse as OID (numeric)
            try:
                semd_oid = int(search_text)
                name, versions, doc_type, link_1520, link_1522, dict_version = self.semd.get_semd_versions(semd_oid)

                if name is None:
                    self.bot.send_message(
                        message.chat.id,
                        f"❌ СЭМД с OID {semd_oid} не найдена.\n\nПопробуйте еще раз или введите корректный OID."
                    )
                    return

                # Format response
                response = (
                    f"🏥 <b>{name}</b>\n\n"
                    f"<b>Доступные версии (v{dict_version}):</b>\n"
                    f"<pre>{versions}</pre>\n\n"
                    f"<b>Справочники НСИ:</b>\n"
                    f"• Все версии этого СЭМД {link_1520}\n"
                    f"• Вид ЭМД этого СЭМД {link_1522}\n"
                )

                markup = get_back_button()
                self.bot.send_message(message.chat.id, response, parse_mode='html', reply_markup=markup)

            except ValueError:
                # Not a number - inform user
                self.bot.send_message(
                    message.chat.id,
                    "⚠️ Пожалуйста введите корректный SEMD OID (число).\n\n"
                    "Примеры:\n"
                    "• 123 - для поиска по номеру\n"
                    "• 456 - для поиска другого документа"
                )

        except Exception as e:
            self.logger.error(f"Error in SEMD search: {e}")
            self.bot.send_message(
                message.chat.id,
                "❌ Ошибка при поиске СЭМД. Пожалуйста попробуйте еще раз."
            )

    def handle_semd_about(self, message: Message):
        """Handle /about command"""
        try:
            about_text = (
                "🔍 <b>SEMD Checker</b>\n\n"
                "<b>Функция:</b> Поиск информации о версиях структурированных электронных медицинских документов (СЭМД)\n\n"
                "<b>Как использовать:</b>\n"
                "1. Отправьте номер СЭМД OID\n"
                "2. Получите список доступных версий\n"
                "3. Посмотрите даты начала и завершения использования\n\n"
                "<b>Версия:</b> 1.0.0"
            )

            markup = get_back_button()
            self.bot.send_message(message.chat.id, about_text, parse_mode='html', reply_markup=markup)

        except Exception as e:
            self.logger.error(f"Error in about handler: {e}")
            self.bot.send_message(
                message.chat.id,
                "❌ Ошибка при получении информации"
            )

    def handle_semd_menu(self, call: CallbackQuery):
        """Handle menu button click for SEMD Checker plugin"""
        try:
            menu_text = (
                "🔍 <b>Поиск версий СЭМД</b>\n\n"
                "<b>Функция:</b> Поиск информации о версиях структурированных электронных медицинских документов (СЭМД)\n\n"
                "<b>Как использовать:</b>\n"
                "1. Отправьте номер СЭМД OID\n"
                "2. Получите список доступных версий\n"
                "3. Посмотрите даты начала и завершения использования\n\n"
                "<b>Версия:</b> 1.0.0"
            )

            markup = get_back_button()
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=menu_text,
                parse_mode='html',
                reply_markup=markup
            )
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            self.logger.error(f"Error in SEMD menu handler: {e}")
            self.bot.answer_callback_query(call.id, "❌ Ошибка при обработке запроса", show_alert=True)

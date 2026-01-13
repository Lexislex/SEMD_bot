"""SEMD Checker plugin handlers"""

import logging
from dataclasses import dataclass

from cachetools import TTLCache
from telebot.types import CallbackQuery, Message

from services.database_service import add_log
from utils.message_manager import cleanup_previous_message, get_message_manager

from .keyboards import get_back_button, get_search_results_keyboard
from .semd_logic import SEMD1520  # TODO сделать класс общим

logger = logging.getLogger(__name__)


@dataclass
class SearchCache:
    """Cached search results for pagination"""

    query: str
    results: list[tuple[int, str]]
    total: int


class SEMDHandlers:
    # Page size for search results
    PAGE_SIZE = 5
    # Cache settings
    _CACHE_MAXSIZE = 100
    _CACHE_TTL = 300  # 5 minutes

    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.semd = SEMD1520()
        # Store search results per user for pagination (TTLCache with auto-expiry)
        self._user_searches: TTLCache[int, SearchCache] = TTLCache(
            maxsize=self._CACHE_MAXSIZE, ttl=self._CACHE_TTL
        )

    def handle_semd_search(self, message: Message):
        """Handle text messages - search for SEMD by OID or name"""
        try:
            # Ignore commands (they start with /)
            if message.text.startswith("/"):
                return

            # Log the activity
            add_log(message)

            # Remove keyboard from previous message
            cleanup_previous_message(self.bot, message.chat.id)

            search_text = message.text.strip()

            # Try to parse as OID (numeric)
            try:
                semd_oid = int(search_text)
                name, versions, doc_type, link_1520, link_1522, dict_version = (
                    self.semd.get_semd_versions(semd_oid)
                )

                if name is None:
                    markup = get_back_button()
                    sent_msg = self.bot.send_message(
                        message.chat.id,
                        f"❌ СЭМД с OID {semd_oid} не найдена.\n\nПопробуйте еще раз или введите корректный OID.",
                        reply_markup=markup,
                    )
                    # Track this message for later cleanup
                    get_message_manager().update_message(
                        message.chat.id, sent_msg.message_id, message.from_user.id
                    )
                    return

                # Format response
                response = (
                    f"🏥 <b>{name}</b>\n\n"
                    f"<b>Доступные версии (v{dict_version}):</b>\n"
                    f"<pre>{versions}</pre>\n\n"
                    f"<b>Справочники НСИ:</b>\n"
                    f"• Все версии этого СЭМД {link_1520}\n"
                    f"• Вид ЭМД этого СЭМД {link_1522}\n\n"
                    f"<i>Введите OID или название для нового поиска</i>"
                )

                markup = get_back_button()
                sent_msg = self.bot.send_message(
                    message.chat.id, response, parse_mode="html", reply_markup=markup
                )
                # Track this message for later cleanup
                get_message_manager().update_message(
                    message.chat.id, sent_msg.message_id, message.from_user.id
                )

            except ValueError:
                # Not a number - try text search
                # Get ALL results at once (for caching), then paginate
                all_results, total_count = self.semd.search_by_name(search_text)

                if not all_results:
                    markup = get_back_button()
                    sent_msg = self.bot.send_message(
                        message.chat.id,
                        f"❌ По запросу «{search_text}» ничего не найдено.\n\n"
                        "Попробуйте другой запрос или введите OID СЭМД (число).",
                        reply_markup=markup,
                    )
                    get_message_manager().update_message(
                        message.chat.id, sent_msg.message_id, message.from_user.id
                    )
                    return

                # Cache all results for pagination (no repeated searches needed)
                self._user_searches[message.from_user.id] = SearchCache(
                    query=search_text,
                    results=all_results,
                    total=total_count,
                )

                # Show first page of results
                first_page = all_results[: self.PAGE_SIZE]
                markup = get_search_results_keyboard(
                    first_page,
                    total_count=total_count,
                    current_offset=0,
                    page_size=self.PAGE_SIZE,
                )
                sent_msg = self.bot.send_message(
                    message.chat.id,
                    f"🔍 Результаты поиска по «{search_text}» ({total_count} найдено):\n\n"
                    "Выберите вид документа или введите новый запрос:",
                    reply_markup=markup,
                )
                get_message_manager().update_message(
                    message.chat.id, sent_msg.message_id, message.from_user.id
                )

        except Exception as e:
            logger.error(f"Error in SEMD search: {e}")
            markup = get_back_button()
            sent_msg = self.bot.send_message(
                message.chat.id,
                "❌ Ошибка при поиске СЭМД. Пожалуйста попробуйте еще раз.",
                reply_markup=markup,
            )
            # Track this message for later cleanup
            get_message_manager().update_message(
                message.chat.id, sent_msg.message_id, message.from_user.id
            )

    def handle_semd_about(self, message: Message):
        """Handle /about command"""
        try:
            # Remove keyboard from previous message
            cleanup_previous_message(self.bot, message.chat.id)

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
            sent_msg = self.bot.send_message(
                message.chat.id, about_text, parse_mode="html", reply_markup=markup
            )
            # Track this message for later cleanup
            get_message_manager().update_message(
                message.chat.id, sent_msg.message_id, message.from_user.id
            )

        except Exception as e:
            logger.error(f"Error in about handler: {e}")
            markup = get_back_button()
            sent_msg = self.bot.send_message(
                message.chat.id,
                "❌ Ошибка при получении информации",
                reply_markup=markup,
            )
            # Track this message for later cleanup
            get_message_manager().update_message(
                message.chat.id, sent_msg.message_id, message.from_user.id
            )

    def handle_semd_menu(self, call: CallbackQuery):
        """Handle menu button click for SEMD Checker plugin"""
        try:
            # Remove keyboard from previous message
            cleanup_previous_message(self.bot, call.message.chat.id)

            menu_text = (
                "🔍 <b>Поиск версий СЭМД</b>\n\n"
                "<b>Функция:</b> Поиск информации о версиях структурированных электронных медицинских документов (СЭМД)\n\n"
                "<b>Как использовать:</b>\n"
                "1. Отправьте номер СЭМД OID или название\n"
                "2. Получите список доступных версий\n"
                "3. Посмотрите даты начала и завершения использования\n\n"
                "<b>Версия:</b> 1.2.0"
            )

            markup = get_back_button()
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=menu_text,
                parse_mode="html",
                reply_markup=markup,
            )
            # Update tracked message to current one
            get_message_manager().update_message(
                call.message.chat.id, call.message.message_id, call.from_user.id
            )
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error in SEMD menu handler: {e}")
            self.bot.answer_callback_query(
                call.id, "❌ Ошибка при обработке запроса", show_alert=True
            )

    def handle_search_result_click(self, call: CallbackQuery):
        """Handle click on search result button"""
        try:
            # Parse callback data: "semd_t:{TYPE}"
            doc_type = int(call.data.split(":")[1])

            # Get versions for this TYPE
            name, versions, dtype, link_1520, link_1522, dict_version = (
                self.semd.get_semd_versions_by_type(doc_type)
            )

            if name is None:
                markup = get_back_button()
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"❌ {versions}",
                    reply_markup=markup,
                )
                get_message_manager().update_message(
                    call.message.chat.id, call.message.message_id, call.from_user.id
                )
                self.bot.answer_callback_query(call.id)
                return

            # Format response (same as OID search)
            response = (
                f"🏥 <b>{name}</b>\n\n"
                f"<b>Доступные версии (v{dict_version}):</b>\n"
                f"<pre>{versions}</pre>\n\n"
                f"<b>Справочники НСИ:</b>\n"
                f"• Все версии этого СЭМД {link_1520}\n"
                f"• Вид ЭМД этого СЭМД {link_1522}\n\n"
                f"<i>Введите OID или название для нового поиска</i>"
            )

            markup = get_back_button()
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=response,
                parse_mode="html",
                reply_markup=markup,
            )
            get_message_manager().update_message(
                call.message.chat.id, call.message.message_id, call.from_user.id
            )
            self.bot.answer_callback_query(call.id)

        except Exception as e:
            logger.error(f"Error in search result handler: {e}")
            self.bot.answer_callback_query(
                call.id, "❌ Ошибка при обработке запроса", show_alert=True
            )

    def handle_pagination(self, call: CallbackQuery):
        """Handle pagination button clicks"""
        try:
            # Parse callback data: "semd_p:{offset}"
            offset = int(call.data.split(":")[1])
            user_id = call.from_user.id

            # Get cached search results (no repeated search needed)
            cache = self._user_searches.get(user_id)
            if not cache:
                self.bot.answer_callback_query(
                    call.id,
                    "Поиск устарел. Введите запрос заново.",
                    show_alert=True,
                )
                return

            # Get page from cached results (instant, no search)
            page_results = cache.results[offset : offset + self.PAGE_SIZE]

            if not page_results:
                self.bot.answer_callback_query(call.id, "Нет результатов")
                return

            # Update keyboard with new page
            markup = get_search_results_keyboard(
                page_results,
                total_count=cache.total,
                current_offset=offset,
                page_size=self.PAGE_SIZE,
            )

            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"🔍 Результаты поиска по «{cache.query}» ({cache.total} найдено):\n\n"
                "Выберите вид документа или введите новый запрос:",
                reply_markup=markup,
            )
            get_message_manager().update_message(
                call.message.chat.id, call.message.message_id, call.from_user.id
            )
            self.bot.answer_callback_query(call.id)

        except Exception as e:
            logger.error(f"Error in pagination handler: {e}")
            self.bot.answer_callback_query(
                call.id, "❌ Ошибка при обработке запроса", show_alert=True
            )

    def handle_noop(self, call: CallbackQuery):
        """Handle noop callback (page indicator button)"""
        self.bot.answer_callback_query(call.id)

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from telebot import apihelper
from telebot.types import CallbackQuery

from services.fnsi_client import nsi_passport_updater
from utils.message_manager import get_message_manager

from .data import NSI_DICTIONARIES, NSI_LIST
from .formatters import (
    DefaultUpdateFormatter,
    ImportantUpdateFormatter,
    MinorUpdateFormatter,
)


class NSIUpdHandlers:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Инициализируем форматеры для каждого стиля
        # 'important' - для критических справочников с полной информацией
        # 'normal' - для обычных справочников в укороченном формате
        # 'minor' - для часто обновляемых справочников
        self.formatters = {
            "important": ImportantUpdateFormatter(),
            "normal": DefaultUpdateFormatter(),
            "minor": MinorUpdateFormatter(),
        }

    def _get_formatter(self, nsi_oid: str):
        """
        Получает форматер для справочника на основе его стиля.

        Args:
            nsi_oid: OID справочника

        Returns:
            UpdateMessageFormatter: экземпляр подходящего форматера
        """
        if nsi_oid not in NSI_DICTIONARIES:
            self.logger.warning(
                f"Справочник {nsi_oid} не найден в конфигурации, используется стандартный форматер"
            )
            return self.formatters["normal"]

        style = NSI_DICTIONARIES[nsi_oid].get("style", "normal")
        formatter = self.formatters.get(style, self.formatters["normal"])

        return formatter

    def _check_single_dictionary(self, nsi_oid: str):
        """
        Проверяет обновления для одного справочника и отправляет уведомления.
        Используется внутри ThreadPoolExecutor для параллельной проверки.
        """
        try:
            updated, fnsi_info = nsi_passport_updater(nsi_oid)
            if not updated or not fnsi_info:
                return

            # Проверяем включены ли уведомления для этого справочника
            if nsi_oid in NSI_DICTIONARIES:
                should_notify = NSI_DICTIONARIES[nsi_oid].get("notify", True)
                if not should_notify:
                    self.logger.debug(
                        f"Уведомления отключены для справочника {nsi_oid}, пропускаем"
                    )
                    return

            # Выбираем форматер на основе стиля справочника
            formatter = self._get_formatter(nsi_oid)

            # Формируем сообщение об обновлении (передаем OID для хэштегов)
            message = formatter.format(fnsi_info, nsi_oid)

            # Определяем нужно ли отправлять со звуком
            silent = formatter.should_send_silent(nsi_oid)

            # Отправляем во все чаты из списка рассылки
            for chat_id in self.config.accounts.updates_mailing_list:
                try:
                    self.bot.send_message(
                        chat_id,
                        message,
                        parse_mode="html",
                        disable_web_page_preview=True,
                        disable_notification=silent,
                    )
                    mode = "без звука" if silent else "со звуком"
                    self.logger.debug(
                        f"Уведомление об обновлении {nsi_oid} отправлено в чат {chat_id} ({mode})"
                    )
                except apihelper.ApiTelegramException as e:
                    self.logger.error(
                        f"Не удалось отправить сообщение в чат {chat_id}: {e}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Непредвиденная ошибка при отправке сообщения в чат {chat_id}: {e}"
                    )

        except Exception as e:
            self.logger.error(
                f"Ошибка при проверке обновлений для справочника {nsi_oid}: {e}"
            )

    def check_updates(self):
        """
        Проверка обновлений НСИ справочников.

        Проверяет справочники параллельно в нескольких потоках,
        чтобы уменьшить общее время цикла при нестабильном соединении с ФНСИ.
        """
        # FNSI плохо справляется с большим числом параллельных запросов
        # с одного IP. 2 потока + небольшая рассылка запусков снижает
        # вероятность получения таймаутов со стороны сервера.
        max_workers = min(2, len(NSI_LIST))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for nsi_oid in NSI_LIST:
                futures[
                    executor.submit(self._check_single_dictionary, nsi_oid)
                ] = nsi_oid
                # Небольшая задержка между постановкой задач в очередь,
                # чтобы не атаковать ФНСИ пачкой одновременных запросов.
                time.sleep(0.3)
            for future in as_completed(futures):
                nsi_oid = futures[future]
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(
                        f"Неожиданная ошибка при проверке справочника {nsi_oid}: {e}"
                    )

    def handle_nsi_checker_menu(self, call: CallbackQuery):
        """
        Handle the NSI Update Checker menu button click.
        Shows information about where updates are posted.

        Args:
            call: CallbackQuery object from Telegram
        """
        try:
            info_text = (
                "📢 <b>Монитор обновлений справочников НСИ</b>\n\n"
                "Обновления справочников НСИ публикуются в канал:\n"
                "<b>«СЭМД инфо»</b>\n\n"
                "🔗 Приглашение в канал:\n"
                "https://t.me/+QGan41q3n6U1MzJi\n\n"
                f"✅ Мониторим обновления {len(NSI_LIST)} справочников.\n\n"
                "Для получения уведомлений подпишитесь на канал!"
            )

            # Import here to avoid circular imports
            from .keyboards import get_back_button

            markup = get_back_button()

            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=info_text,
                parse_mode="html",
                reply_markup=markup,
            )
            # Update tracked message to current one
            get_message_manager().update_message(
                call.message.chat.id, call.message.message_id, call.from_user.id
            )
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            self.logger.error(f"Ошибка при обработке меню NSI Update Checker: {e}")
            self.bot.answer_callback_query(
                call.id, "❌ Ошибка при обработке запроса", show_alert=True
            )

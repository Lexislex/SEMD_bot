import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from telebot import apihelper
from telebot.types import CallbackQuery

from services.database_service import add_nsi_passport
from services.fnsi_client import fetch_new_version
from services.notification_store import NotificationStore
from utils.message_manager import get_message_manager

from .data import NSI_DICTIONARIES, NSI_LIST, notified_count
from .formatters import (
    DefaultUpdateFormatter,
    ImportantUpdateFormatter,
    MinorUpdateFormatter,
)

# 400 — сообщение не принято (например, битый HTML), 403 — бот удалён из чата
# или заблокирован: повтор не поможет
PERMANENT_TELEGRAM_ERRORS = {400, 403}


class NSIUpdHandlers:
    def __init__(self, bot, config, store: NotificationStore | None = None):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.store = store or NotificationStore(config.paths.fnsi_db_path)

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
        Проверяет обновление одного справочника и ставит уведомление в очередь.
        Используется внутри ThreadPoolExecutor для параллельной проверки.

        Паспорт новой версии и задание на уведомление записываются одной
        транзакцией; отправка — отдельно, в deliver_pending().
        """
        try:
            fnsi_info = fetch_new_version(nsi_oid)
            if not fnsi_info:
                return

            # Справочники без уведомлений (например, 638 для schematron_monitor) —
            # только паспорт, без задания
            if not NSI_DICTIONARIES.get(nsi_oid, {}).get("notify", True):
                add_nsi_passport(fnsi_info)
                self.logger.debug(
                    f"Уведомления отключены для справочника {nsi_oid}, сохранён только паспорт"
                )
                return

            message = self._get_formatter(nsi_oid).format(fnsi_info, nsi_oid)
            chats = self.config.accounts.updates_mailing_list
            job_id = self.store.create_job(fnsi_info, message, chats)
            if job_id is None:
                self.logger.debug(
                    f"Версия {fnsi_info['version']} справочника {nsi_oid} уже известна"
                )
            elif not chats:
                self.logger.warning(
                    f"UPDS_MAILING_LIST пуст — уведомление об обновлении {nsi_oid} некуда отправить"
                )
            else:
                self.logger.info(
                    f"Обновление {nsi_oid} до {fnsi_info['version']}: задание {job_id}"
                )
        except Exception as e:
            self.logger.error(
                f"Ошибка при проверке обновлений для справочника {nsi_oid}: {e}"
            )

    def deliver_pending(self) -> int:
        """
        Отправляет уведомления, время доставки которых наступило.

        Вызывается после каждого цикла проверки и отдельной частой задачей
        планировщика, поэтому недоставленное досылается и без новых версий.
        Планировщик выполняет задачи последовательно в одном потоке, так что
        параллельных отправщиков нет.

        Returns:
            Количество доставленных сообщений.
        """
        sent = 0
        for delivery in self.store.due_deliveries():
            silent = self._get_formatter(delivery.dictionary).should_send_silent(
                delivery.dictionary
            )
            try:
                message = self.bot.send_message(
                    delivery.chat_id,
                    delivery.payload,
                    parse_mode="html",
                    disable_web_page_preview=True,
                    disable_notification=silent,
                )
            except apihelper.ApiTelegramException as e:
                self._handle_telegram_error(delivery, e)
                continue
            except Exception as e:
                # сеть, таймаут и прочее — временная ошибка
                self._retry(delivery, f"{type(e).__name__}: {e}")
                continue

            self.store.mark_sent(delivery, getattr(message, "message_id", None))
            sent += 1
            self.logger.debug(
                f"Уведомление об обновлении {delivery.dictionary} {delivery.version} "
                f"отправлено в чат {delivery.chat_id}"
            )
        return sent

    def _handle_telegram_error(self, delivery, error: apihelper.ApiTelegramException):
        code = error.error_code
        if code == 429:
            parameters = (error.result_json or {}).get("parameters") or {}
            retry_after = parameters.get("retry_after")
            self._retry(
                delivery,
                str(error),
                timedelta(seconds=retry_after) if retry_after else None,
            )
        elif code in PERMANENT_TELEGRAM_ERRORS:
            # повтор не поможет: битый HTML, бот удалён из чата, чат не найден
            self.store.mark_failed(delivery, str(error))
            self.logger.error(
                f"Уведомление об обновлении {delivery.dictionary} {delivery.version} "
                f"не доставлено в чат {delivery.chat_id}: {error}"
            )
        else:
            self._retry(delivery, str(error))

    def _retry(self, delivery, error: str, retry_after: timedelta | None = None):
        if self.store.mark_retry(delivery, error, retry_after=retry_after):
            self.logger.warning(
                f"Не удалось отправить уведомление об обновлении {delivery.dictionary} "
                f"в чат {delivery.chat_id}, повторим позже: {error}"
            )
        else:
            self.logger.error(
                f"Уведомление об обновлении {delivery.dictionary} {delivery.version} "
                f"так и не доставлено в чат {delivery.chat_id}: {error}"
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
                futures[executor.submit(self._check_single_dictionary, nsi_oid)] = (
                    nsi_oid
                )
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

        # Новые задания отправляем сразу, не дожидаясь задачи доставки
        self.deliver_pending()

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
                f"✅ Присылаем уведомления об обновлениях {notified_count()} справочников.\n\n"
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

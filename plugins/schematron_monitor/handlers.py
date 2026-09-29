import io
import logging
import posixpath
from datetime import datetime
from html import escape
from typing import List, Optional, Tuple

from telebot.types import CallbackQuery

from services.gitlab_client import GitLabClient
from services.schematron_store import (
    STATUS_ERROR,
    STATUS_NO_GIT_LINK,
    STATUS_NO_SCHEMATRON,
    STATUS_NOT_IN_1520,
    STATUS_OK,
    STATUS_REPO_NOT_FOUND,
    SchematronStore,
)
from utils.message_manager import get_message_manager

from .data import WATCHED_SEMD
from .formatters import (
    build_diff_text,
    diff_file_name,
    format_change_message,
    is_night,
    with_inline_diff,
)
from .monitor import NotificationError, SchematronChange, SchematronMonitor

STATUS_LABELS = {
    STATUS_OK: "✅",
    STATUS_NO_SCHEMATRON: "⚪️ нет схематрона",
    STATUS_REPO_NOT_FOUND: "⚠️ репозиторий недоступен",
    STATUS_NOT_IN_1520: "⚠️ нет в 1520",
    STATUS_NO_GIT_LINK: "⚠️ нет GIT_LINK",
    STATUS_ERROR: "❌ ошибка",
}
MENU_NAME_LIMIT = 45
# Лимит Telegram Bot API на отправку файла — 50 МБ, держим запас
MAX_DOCUMENT_BYTES = 45 * 1024 * 1024


class SchematronHandlers:
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)

        from plugins.semd_checker.semd_logic import get_semd638, get_semd1520

        self.semd1520 = get_semd1520()
        self.semd638 = get_semd638()
        self.client = GitLabClient.from_config(config)
        self.store = SchematronStore(config.paths.fnsi_db_path)
        self.monitor = SchematronMonitor(
            client=self.client,
            store=self.store,
            semd_lookup=self.semd1520.get_semd_info,
            notify=self.send_change,
            package_lookup=self.semd638.get_git_link,
        )

    def check_updates(self):
        """Проверка изменений схематронов для всех отслеживаемых СЭМД."""
        changes = self.monitor.check_all(WATCHED_SEMD)
        if changes:
            self.logger.info(
                f"Отправлено уведомлений об изменении схематронов: {len(changes)}"
            )

    def send_change(self, change: SchematronChange):
        """
        Отправляет уведомление об изменении схематрона во все чаты рассылки.

        Доставкой считается отправка текста; ошибки вложений логируются,
        но не блокируют сдвиг baseline (ссылки на GitLab есть в тексте).

        Raises:
            NotificationError: если текст не доставлен ни в один чат
                (в т.ч. пустой UPDS_MAILING_LIST) — тогда монитор не сдвигает
                baseline и повторит попытку в следующем цикле.
        """
        chats = self.config.accounts.updates_mailing_list
        if not chats:
            raise NotificationError(
                "UPDS_MAILING_LIST пуст — уведомление о схематроне некуда отправить"
            )

        message = with_inline_diff(format_change_message(change, self.client), change)
        documents = self._build_documents(change)
        silent = is_night()

        delivered = 0
        for chat_id in chats:
            try:
                self.bot.send_message(
                    chat_id,
                    message,
                    parse_mode="html",
                    disable_web_page_preview=True,
                    disable_notification=silent,
                )
            except Exception as e:
                self.logger.error(
                    f"Не удалось отправить уведомление о схематроне в чат {chat_id}: {e}"
                )
                continue
            delivered += 1

            for file_name, content in documents:
                try:
                    self.bot.send_document(
                        chat_id,
                        io.BytesIO(content),
                        visible_file_name=file_name,
                        disable_notification=True,
                    )
                except Exception as e:
                    self.logger.error(
                        f"Не удалось отправить файл {file_name} в чат {chat_id}: {e}"
                    )

        if delivered == 0:
            raise NotificationError(
                f"уведомление об изменении схематрона СЭМД {change.semd_oid} "
                f"не доставлено ни в один чат"
            )

    def _build_documents(self, change: SchematronChange) -> List[Tuple[str, bytes]]:
        """Files to attach: .diff and full schematron files, within the size limit."""
        documents = []
        if change.diffs:
            documents.append(
                (diff_file_name(change), build_diff_text(change).encode("utf-8"))
            )
        # Полные файлы — когда сравнение недоступно или diff слишком большой
        documents += [
            (posixpath.basename(path), content) for path, content in change.attachments
        ]

        allowed = []
        for file_name, content in documents:
            if len(content) > MAX_DOCUMENT_BYTES:
                self.logger.warning(
                    f"Файл {file_name} ({len(content)} байт) превышает лимит Telegram, "
                    f"не отправляется — см. ссылки на GitLab в сообщении"
                )
                continue
            allowed.append((file_name, content))
        return allowed

    def _semd_name(self, semd_oid: str) -> str:
        info = self.semd1520.get_semd_info(semd_oid)
        name = (info or {}).get("NAME") or ""
        return (
            name if len(name) <= MENU_NAME_LIMIT else name[: MENU_NAME_LIMIT - 1] + "…"
        )

    @staticmethod
    def _format_dt(iso_value: Optional[str], fmt: str) -> str:
        if not iso_value:
            return ""
        try:
            return datetime.fromisoformat(iso_value).strftime(fmt)
        except ValueError:
            return iso_value

    def build_menu_text(self) -> str:
        states = self.store.get_all()
        checked = [s.last_checked for s in states.values() if s.last_checked]
        last_check = (
            self._format_dt(max(checked), "%d.%m.%Y %H:%M")
            if checked
            else "ещё не было"
        )

        lines = [
            "🧩 <b>Мониторинг схематронов СЭМД</b>",
            "",
            f"Отслеживаем изменения схематронов в GitLab Минздрава для {len(WATCHED_SEMD)} СЭМД.",
            "Уведомления публикуются в канал <b>«СЭМД инфо»</b>:",
            "https://t.me/+QGan41q3n6U1MzJi",
            "",
            f"Последняя проверка: {last_check}",
            "",
        ]
        for semd_oid in WATCHED_SEMD:
            state = states.get(semd_oid)
            label = STATUS_LABELS.get(state.status, state.status) if state else "⏳"
            changed = ""
            if state and state.last_changed:
                changed = f" (изм. {self._format_dt(state.last_changed, '%d.%m.%Y')})"
            lines.append(
                f"• <code>{escape(semd_oid)}</code> {label} {escape(self._semd_name(semd_oid))}{changed}"
            )
        return "\n".join(lines)

    def handle_menu(self, call: CallbackQuery):
        """Показывает список отслеживаемых СЭМД и статус последней проверки."""
        try:
            from .keyboards import get_back_button

            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=self.build_menu_text(),
                parse_mode="html",
                reply_markup=get_back_button(),
                disable_web_page_preview=True,
            )
            get_message_manager().update_message(
                call.message.chat.id, call.message.message_id, call.from_user.id
            )
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            self.logger.error(f"Ошибка при обработке меню Schematron Monitor: {e}")
            self.bot.answer_callback_query(
                call.id, "❌ Ошибка при обработке запроса", show_alert=True
            )

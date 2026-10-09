import pytest

from plugins.nsi_update_checker.data import NSI_DICTIONARIES, notified_count
from plugins.nsi_update_checker.formatters import (
    DefaultUpdateFormatter,
    ImportantUpdateFormatter,
    MinorUpdateFormatter,
)

FNSI_INFO = {
    "id": "1.2.643.5.1.13.13.11.1520",
    "fullName": "Электронные медицинские документы",
    "shortName": "ЭМД <R&D>",
    "lastUpdate": "2026-09-15T15:27:00",
    "version": "12.96",
    "releaseNotes": "Добавлено: 2; Изменено: <3>;",
}


@pytest.mark.parametrize(
    "formatter, title",
    [
        (ImportantUpdateFormatter(), "Важное обновление"),
        (DefaultUpdateFormatter(), "Обновление справочника"),
    ],
)
def test_full_formatter_escapes_fnsi_data(formatter, title):
    message = formatter.format(FNSI_INFO, FNSI_INFO["id"])

    assert title in message
    assert "ЭМД &lt;R&amp;D&gt;" in message
    assert "Изменено: &lt;3&gt;" in message
    assert "<R&D>" not in message
    assert "passport/12.96" in message
    assert "#сен2026" in message


def test_minor_formatter_escapes_fnsi_data():
    message = MinorUpdateFormatter().format(FNSI_INFO)
    assert "<b>ЭМД &lt;R&amp;D&gt;</b> v12.96" in message


def test_hashtags_survive_bad_date():
    tags = DefaultUpdateFormatter().get_hashtags(
        dict(FNSI_INFO, lastUpdate="not a date"), FNSI_INFO["id"]
    )
    assert tags == "#ЭМД__R_D_"


def test_notified_count_skips_silent_dictionaries():
    assert NSI_DICTIONARIES["1.2.643.5.1.13.13.99.2.638"]["notify"] is False
    assert notified_count() == len(NSI_DICTIONARIES) - sum(
        1 for p in NSI_DICTIONARIES.values() if not p.get("notify", True)
    )
    assert notified_count() < len(NSI_DICTIONARIES)


class TestNotificationFlow:
    """Detection -> job -> delivery in NSIUpdHandlers."""

    OID = "1.2.643.5.1.13.13.11.1520"
    INFO = dict(FNSI_INFO, version="12.97")

    @pytest.fixture
    def handlers(self, tmp_path):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from plugins.nsi_update_checker.handlers import NSIUpdHandlers
        from services.notification_store import NotificationStore

        config = SimpleNamespace(
            accounts=SimpleNamespace(updates_mailing_list=[10, 20]),
            paths=SimpleNamespace(fnsi_db_path=tmp_path / "fnsi.sqlite"),
        )
        bot = MagicMock()
        bot.send_message.return_value = SimpleNamespace(message_id=555)
        store = NotificationStore(config.paths.fnsi_db_path)
        return NSIUpdHandlers(bot, config, store=store)

    def detect(self, handlers, oid=OID, info=INFO):
        from unittest.mock import patch

        with patch(
            "plugins.nsi_update_checker.handlers.fetch_new_version", return_value=info
        ):
            handlers._check_single_dictionary(oid)

    def test_new_version_is_queued_and_delivered(self, handlers):
        self.detect(handlers)
        handlers.bot.send_message.assert_not_called()  # detection does not send

        assert handlers.deliver_pending() == 2

        chats = [c.args[0] for c in handlers.bot.send_message.call_args_list]
        assert chats == [10, 20]
        assert "12.97" in handlers.bot.send_message.call_args.args[1]
        assert handlers.deliver_pending() == 0

    def test_known_version_is_not_queued_twice(self, handlers):
        self.detect(handlers)
        self.detect(handlers)
        assert handlers.deliver_pending() == 2

    def test_silent_dictionary_stores_passport_only(self, handlers):
        from plugins.nsi_update_checker.data import NSI_DICTIONARIES

        silent = next(
            o for o, p in NSI_DICTIONARIES.items() if not p.get("notify", True)
        )
        info = dict(self.INFO, id=silent)
        with pytest.MonkeyPatch.context() as mp:
            added = []
            mp.setattr(
                "plugins.nsi_update_checker.handlers.add_nsi_passport", added.append
            )
            self.detect(handlers, oid=silent, info=info)
        assert added == [info]
        assert handlers.store.due_deliveries() == []

    def test_transient_error_retries_only_that_chat(self, handlers):
        from datetime import timedelta

        from services.notification_store import RETRY_DELAYS, utc_now

        self.detect(handlers)
        handlers.bot.send_message.side_effect = [
            ConnectionError("down"),
            handlers.bot.send_message.return_value,
        ]

        assert handlers.deliver_pending() == 1
        due = handlers.store.due_deliveries(
            now=utc_now() + RETRY_DELAYS[0] + timedelta(seconds=5)
        )
        assert [d.chat_id for d in due] == [10]

    @pytest.mark.parametrize(
        "code, expected_due", [(400, 0), (403, 0), (429, 1), (502, 1)]
    )
    def test_telegram_errors(self, handlers, code, expected_due):
        from datetime import timedelta

        from telebot.apihelper import ApiTelegramException

        from services.notification_store import utc_now

        self.detect(handlers)
        error = ApiTelegramException(
            "sendMessage",
            None,
            {"error_code": code, "description": "x", "parameters": {"retry_after": 3}},
        )
        handlers.bot.send_message.side_effect = error

        assert handlers.deliver_pending() == 0

        later = handlers.store.due_deliveries(now=utc_now() + timedelta(hours=1))
        assert len(later) == expected_due * 2

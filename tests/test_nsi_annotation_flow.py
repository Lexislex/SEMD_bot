"""Budgeted FNSI transport and the annotation step of notification jobs."""

import json
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from plugins.nsi_update_checker import handlers as handlers_module
from plugins.nsi_update_checker.annotation_1520 import (
    OID_1520,
    Annotation,
    AnnotationUnavailable,
)
from plugins.nsi_update_checker.handlers import NSIUpdHandlers
from services.fnsi_client import FnsiApi, FnsiApiError, FnsiBudgetExceeded
from services.notification_store import NotificationStore, utc_now

INFO = {
    "id": OID_1520,
    "fullName": "Электронные медицинские документы",
    "shortName": "ЭМД",
    "lastUpdate": "2026-09-30T15:23:00",
    "version": "12.96",
    "releaseNotes": "Добавлено записей: 3;",
}


# ------------------------------------------------------------------ transport


def response(status=200, payload=None, chunks=None):
    """Streamed response: the body is read through raw.read1."""
    resp = MagicMock(status_code=status)
    body = json.dumps(
        payload if payload is not None else {"result": "OK", "list": []}
    ).encode()
    parts = list(chunks) if chunks is not None else [body]
    resp.raw.read1.side_effect = lambda *a, **k: parts.pop(0) if parts else b""
    return resp


@pytest.fixture
def no_sleep():
    with patch("services.fnsi_client.sleep"):
        yield


class TestFnsiApi:
    def make(self, responses, deadline=60.0, **kwargs):
        session = MagicMock()
        session.get.side_effect = responses
        api = FnsiApi(OID_1520, time.monotonic() + deadline, session=session, **kwargs)
        return api, session

    def test_ok(self):
        api, session = self.make([response(payload={"result": "OK", "list": [1]})])

        assert api.get("versions", page=1)["list"] == [1]
        params = session.get.call_args.kwargs["params"]
        assert params["identifier"] == OID_1520 and params["page"] == 1

    def test_retries_5xx_then_ok(self, no_sleep):
        api, session = self.make([response(503), response()])

        assert api.get("compare")["result"] == "OK"
        assert session.get.call_count == 2

    def test_timeout_capped_by_remaining_budget(self):
        api, session = self.make([response()], deadline=5)

        api.get("versions")

        assert session.get.call_args.kwargs["timeout"] <= 5

    def test_budget_exhausted(self):
        api, session = self.make([response()], deadline=0.5)

        with pytest.raises(FnsiBudgetExceeded):
            api.get("versions")
        session.get.assert_not_called()

    def test_request_cap(self):
        api, _ = self.make([response(), response()], max_requests=1)
        api.get("versions")

        with pytest.raises(FnsiBudgetExceeded, match="request budget"):
            api.get("versions")

    def test_error_message_has_no_user_key(self, no_sleep):
        secret_url = "https://nsi.example/port/rest/data?userKey=SECRET-KEY"
        api, _ = self.make([requests.ConnectionError(secret_url)] * 3)

        with pytest.raises(FnsiApiError) as err:
            api.get("data")
        assert "SECRET" not in str(err.value)
        assert "ConnectionError" in str(err.value)

    def test_trickling_body_is_cut_by_deadline(self):
        """Real requests/urllib3 objects; the server sends one byte per socket read.

        iter_content(65536) would only return after the whole 64 KB chunk (or EOF);
        read1 returns after each read, so the budget is checked mid-body.
        """
        import io

        from urllib3.response import HTTPResponse

        now = [0.0]

        class Trickle(io.RawIOBase):
            def __init__(self, data):
                self.data = data

            def readable(self):
                return True

            def readinto(self, buffer):
                if not self.data:
                    return 0
                now[0] += 1.0  # each byte takes a second
                buffer[0] = self.data[0]
                self.data = self.data[1:]
                return 1

        body = json.dumps({"result": "OK", "list": ["x" * 80]}).encode()
        raw = HTTPResponse(
            body=io.BufferedReader(Trickle(body), buffer_size=1),
            preload_content=False,
            status=200,
        )
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = raw
        with patch("services.fnsi_client.monotonic", side_effect=lambda: now[0]):
            api, _ = self.make([resp], deadline=0)
            api.deadline = 10.0
            with pytest.raises(FnsiBudgetExceeded, match="while reading"):
                api.get("compare")
        assert now[0] <= 11  # stopped right after the budget, not after ~100 bytes

    def test_server_text_is_not_in_error(self):
        api, _ = self.make(
            [
                response(
                    payload={
                        "result": "ERROR",
                        "resultCode": 7,
                        "resultText": "denied for userKey=SYNTHETIC-SECRET",
                    }
                )
            ]
        )

        with pytest.raises(FnsiApiError) as err:
            api.get("compare")
        assert "SYNTHETIC" not in str(err.value)
        assert "code 7" in str(err.value)

    @pytest.mark.parametrize(
        "resp",
        [response(404), response(payload={"result": "ERROR", "resultText": "bad"})],
    )
    def test_non_retryable_failures(self, resp):
        api, session = self.make([resp])

        with pytest.raises(FnsiApiError):
            api.get("compare")
        assert session.get.call_count == 1


# --------------------------------------------------------------- job annotation


@pytest.fixture
def make_handlers(tmp_path):
    config = SimpleNamespace(
        accounts=SimpleNamespace(updates_mailing_list=[10, 20]),
        paths=SimpleNamespace(fnsi_db_path=tmp_path / "fnsi.sqlite"),
    )

    def factory():
        bot = MagicMock()
        bot.send_message.return_value = SimpleNamespace(message_id=1)
        store = NotificationStore(config.paths.fnsi_db_path)
        return NSIUpdHandlers(bot, config, store=store)

    return factory


def detect(handlers, annotator):
    with (
        patch.object(handlers_module, "fetch_new_version", return_value=INFO),
        patch.dict(handlers_module.ANNOTATORS, {OID_1520: annotator}, clear=True),
        patch.object(handlers_module, "FnsiApi", MagicMock()),
    ):
        handlers._check_single_dictionary(OID_1520)


def job_row(handlers):
    import sqlite3

    with sqlite3.connect(handlers.store.db_path) as con:
        return con.execute(
            "SELECT status, annotation_status, annotation_reason, payload FROM notification_jobs"
        ).fetchone()


class TestAnnotationStep:
    def test_complete_annotation_is_sent_to_every_chat(self, make_handlers):
        handlers = make_handlers()
        annotator = MagicMock(
            return_value=Annotation("12.95", "➕ <b>Добавлены записи СЭМД (3)</b>")
        )

        detect(handlers, annotator)

        status, annotation_status, _, payload = job_row(handlers)
        assert (status, annotation_status) == ("ready", "complete")
        assert "<code>12.95</code> → <code>12.96</code>" in payload
        assert "Что изменилось" in payload and "Описание изменений" not in payload
        assert annotator.call_args.args[1] == "12.96"
        assert annotator.call_args.kwargs["max_chars"] > 3000

        assert handlers.deliver_pending() == 2
        texts = {c.args[1] for c in handlers.bot.send_message.call_args_list}
        assert texts == {payload}  # same final text for all chats

    @pytest.mark.parametrize(
        "error, expected",
        [
            (AnnotationUnavailable("unsupported operations ['DELETE']"), "skipped"),
            (FnsiApiError("compare: HTTP 503"), "failed"),
            (FnsiBudgetExceeded("versions: time budget exhausted"), "failed"),
            (RuntimeError("bug"), "failed"),
        ],
    )
    def test_failure_sends_plain_notification(self, make_handlers, error, expected):
        handlers = make_handlers()

        detect(handlers, MagicMock(side_effect=error))

        status, annotation_status, reason, payload = job_row(handlers)
        assert (status, annotation_status) == ("ready", expected)
        assert reason
        assert "Описание изменений" in payload  # the plain notification
        assert handlers.deliver_pending() == 2

    def test_too_long_annotation_falls_back(self, make_handlers):
        handlers = make_handlers()

        detect(handlers, MagicMock(return_value=Annotation("12.95", "x" * 5000)))

        _, annotation_status, reason, payload = job_row(handlers)
        assert annotation_status == "skipped"
        assert reason.startswith("message too long")
        assert "Описание изменений" in payload

    def test_preparing_job_is_not_sent_and_released_after_deadline(self, make_handlers):
        # процесс упал во время подготовки аннотации: задание осталось preparing
        handlers = make_handlers()
        handlers.store.create_job(
            INFO,
            "plain text",
            [10],
            annotation_deadline=utc_now() + timedelta(minutes=3),
        )

        assert handlers.deliver_pending() == 0
        handlers.bot.send_message.assert_not_called()

        restarted = make_handlers()
        later = utc_now() + timedelta(minutes=4)
        with patch("services.notification_store.utc_now", return_value=later):
            assert restarted.deliver_pending() == 1
        assert restarted.bot.send_message.call_args.args[1] == "plain text"
        assert job_row(restarted)[:2] == (
            "done",
            "expired",
        )  # единственный чат доставлен

    def test_late_finalize_after_overdue_release_is_ignored(self, make_handlers):
        handlers = make_handlers()
        job_id = handlers.store.create_job(
            INFO, "plain", [10], annotation_deadline=utc_now() - timedelta(seconds=1)
        )
        handlers.store.finalize_overdue()

        assert not handlers.store.finalize_job(job_id, "complete", payload="annotated")
        assert job_row(handlers)[3] == "plain"

    def test_other_dictionaries_are_not_annotated(self, make_handlers):
        handlers = make_handlers()
        info = dict(INFO, id="1.2.643.5.1.13.13.11.1005", shortName="МКБ-10")
        annotator = MagicMock()
        with (
            patch.object(handlers_module, "fetch_new_version", return_value=info),
            patch.dict(handlers_module.ANNOTATORS, {OID_1520: annotator}, clear=True),
        ):
            handlers._check_single_dictionary(info["id"])

        annotator.assert_not_called()
        assert job_row(handlers)[:2] == ("ready", None)


class TestDeadlineAndRedaction:
    def test_annotation_after_deadline_is_not_accepted(self, make_handlers):
        handlers = make_handlers()
        job_id = handlers.store.create_job(
            INFO, "plain", [10], annotation_deadline=utc_now() - timedelta(seconds=1)
        )

        # finalize_overdue ещё не запускался: проверка дедлайна в самом UPDATE
        assert not handlers.store.finalize_job(job_id, "complete", payload="annotated")
        assert handlers.store.finalize_job(job_id, "skipped", reason="late")
        assert job_row(handlers)[3] == "plain"

    def test_late_annotation_falls_back_in_handler(self, make_handlers):
        handlers = make_handlers()

        def slow(*args, **kwargs):
            # аннотация готова, но дедлайн уже прошёл
            later = utc_now() + timedelta(minutes=5)
            patcher = patch("services.notification_store.utc_now", return_value=later)
            patcher.start()
            slow.patcher = patcher
            return Annotation("12.95", "➕ <b>x</b>")

        try:
            detect(handlers, slow)
        finally:
            slow.patcher.stop()

        status, annotation_status, reason, payload = job_row(handlers)
        assert (status, annotation_status) == ("ready", "skipped")
        assert "after the deadline" in reason
        assert "Описание изменений" in payload

    def test_reason_is_redacted(self, make_handlers):
        handlers = make_handlers()

        detect(
            handlers,
            MagicMock(side_effect=RuntimeError("boom userKey=SYNTHETIC-SECRET&x=1")),
        )

        assert "SYNTHETIC" not in job_row(handlers)[2]
        assert "userKey=****" in job_row(handlers)[2]


class TestReviewRegressions:
    def test_counters_are_checked_in_the_real_flow(self, make_handlers):
        """Handler passes FNSI counters to the real 1520 annotator."""
        from plugins.nsi_update_checker.annotation_1520 import build_1520_annotation
        from tests.test_annotation_1520 import FakeApi, compare_key

        def drop_row(data):
            payload = data[compare_key(data, "2026-08-10")]["data"]
            payload["list"].pop()
            payload["total"] = 2  # consistent but incomplete compare

        api = FakeApi(drop_row)
        info = dict(
            INFO,
            releaseNotes="Добавлено записей: 3;\nИзменено записей: 0;\nУдалено записей: 0;",
        )
        handlers = make_handlers()
        with (
            patch.object(handlers_module, "fetch_new_version", return_value=info),
            patch.dict(
                handlers_module.ANNOTATORS,
                {OID_1520: build_1520_annotation},
                clear=True,
            ),
            patch.object(
                handlers_module, "FnsiApi", return_value=MagicMock(get=api.get)
            ),
        ):
            handlers._check_single_dictionary(OID_1520)

        status, annotation_status, reason, payload = job_row(handlers)
        assert annotation_status == "skipped"
        assert "differ from compare" in reason
        assert "Добавлены записи СЭМД (2)" not in payload

    def test_traceback_is_redacted(self, make_handlers, caplog):
        import logging

        handlers = make_handlers()
        with caplog.at_level(logging.WARNING):
            detect(
                handlers,
                MagicMock(side_effect=RuntimeError("userKey=SYNTHETIC-SECRET")),
            )

        rendered = "\n".join(
            logging.Formatter().format(record) for record in caplog.records
        )
        assert "SYNTHETIC" not in rendered
        assert "userKey=****" in rendered

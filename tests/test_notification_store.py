import sqlite3
from datetime import datetime, timedelta, timezone
import pytest

from services.notification_store import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    JOB_DONE,
    JOB_READY,
    MAX_DELIVERY_AGE,
    RETRY_DELAYS,
    NotificationStore,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
INFO = {
    "id": "1.2.643.5.1.13.13.11.1520",
    "fullName": "Электронные медицинские документы",
    "shortName": "ЭМД",
    "lastUpdate": "2026-09-30T15:23:00",
    "version": "12.96",
    "releaseNotes": "Добавлено записей: 3;",
}


@pytest.fixture
def db(tmp_path):
    return tmp_path / "fnsi.sqlite"


@pytest.fixture
def store(db) -> NotificationStore:
    return NotificationStore(db)


def rows(db, sql, *args):
    with sqlite3.connect(db) as con:
        return con.execute(sql, args).fetchall()


class TestCreateJob:
    def test_passport_job_and_deliveries_stored_together(self, store, db):
        job_id = store.create_job(INFO, "<b>text</b>", [10, 20, 10], now=NOW)

        assert job_id is not None
        assert rows(db, "SELECT ID, version FROM nsi_passport") == [
            (INFO["id"], "12.96")
        ]
        assert rows(
            db, "SELECT dictionary, version, payload, status FROM notification_jobs"
        ) == [(INFO["id"], "12.96", "<b>text</b>", JOB_READY)]
        # дубликаты чатов схлопываются
        assert rows(
            db, "SELECT chat_id, status FROM notification_deliveries ORDER BY chat_id"
        ) == [
            (10, DELIVERY_PENDING),
            (20, DELIVERY_PENDING),
        ]

    def test_known_version_creates_nothing(self, store, db):
        store.create_job(INFO, "text", [10], now=NOW)

        assert store.create_job(INFO, "text", [10], now=NOW) is None
        assert len(rows(db, "SELECT * FROM notification_jobs")) == 1
        assert len(rows(db, "SELECT * FROM nsi_passport")) == 1

    def test_failure_rolls_back_passport(self, store, db):
        # если задание не записалось, паспорт тоже не должен остаться —
        # иначе следующий цикл не увидит обновление
        # chat_id NULL нарушает NOT NULL на последней вставке транзакции
        assert store.create_job(INFO, "text", [10, None], now=NOW) is None

        assert rows(db, "SELECT * FROM nsi_passport") == []
        assert rows(db, "SELECT * FROM notification_jobs") == []

    def test_empty_mailing_list_job_is_done(self, store, db):
        store.create_job(INFO, "text", [], now=NOW)

        assert rows(db, "SELECT status FROM notification_jobs") == [(JOB_DONE,)]
        assert store.due_deliveries(now=NOW) == []


class TestDeliveries:
    def test_due_deliveries(self, store):
        store.create_job(INFO, "text", [10, 20], now=NOW)

        due = store.due_deliveries(now=NOW)

        assert [(d.chat_id, d.payload, d.version, d.attempts) for d in due] == [
            (10, "text", "12.96", 0),
            (20, "text", "12.96", 0),
        ]
        assert due[0].job_created_at == NOW

    def test_oldest_job_first(self, store):
        store.create_job(dict(INFO, version="12.97"), "new", [10], now=NOW)
        store.create_job(
            dict(INFO, version="12.96"), "old", [10], now=NOW - timedelta(minutes=5)
        )

        assert [d.payload for d in store.due_deliveries(now=NOW)] == ["old", "new"]

    def test_mark_sent_finishes_job_when_all_sent(self, store, db):
        store.create_job(INFO, "text", [10, 20], now=NOW)
        first, second = store.due_deliveries(now=NOW)

        store.mark_sent(first, 111, now=NOW)
        assert rows(db, "SELECT status FROM notification_jobs") == [(JOB_READY,)]

        store.mark_sent(second, 222, now=NOW)
        assert rows(db, "SELECT status FROM notification_jobs") == [(JOB_DONE,)]
        assert rows(
            db,
            "SELECT chat_id, status, message_id, attempts FROM notification_deliveries ORDER BY chat_id",
        ) == [
            (10, DELIVERY_SENT, 111, 1),
            (20, DELIVERY_SENT, 222, 1),
        ]
        assert store.due_deliveries(now=NOW) == []

    def test_retry_only_failed_chat(self, store):
        store.create_job(INFO, "text", [10, 20], now=NOW)
        ok, broken = store.due_deliveries(now=NOW)
        store.mark_sent(ok, 1, now=NOW)

        assert store.mark_retry(broken, "502 Bad Gateway", now=NOW)

        assert store.due_deliveries(now=NOW) == []
        due = store.due_deliveries(now=NOW + RETRY_DELAYS[0])
        assert [(d.chat_id, d.attempts) for d in due] == [(20, 1)]

    def test_retry_delays_grow(self, store):
        store.create_job(INFO, "text", [10], now=NOW)
        moment = NOW
        for expected in RETRY_DELAYS[:4]:
            (delivery,) = store.due_deliveries(now=moment)
            assert store.mark_retry(delivery, "err", now=moment)
            assert (
                store.due_deliveries(now=moment + expected - timedelta(seconds=1)) == []
            )
            moment += expected

    def test_retry_after_overrides_schedule(self, store):
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)

        store.mark_retry(delivery, "429", now=NOW, retry_after=timedelta(seconds=7))

        assert len(store.due_deliveries(now=NOW + timedelta(seconds=7))) == 1

    def test_gives_up_after_max_age(self, store, db):
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)
        late = NOW + MAX_DELIVERY_AGE - timedelta(seconds=30)  # +1 мин уже за пределом

        assert not store.mark_retry(delivery, "still down", now=late)

        assert rows(db, "SELECT status, last_error FROM notification_deliveries") == [
            (DELIVERY_FAILED, "still down")
        ]
        assert rows(db, "SELECT status FROM notification_jobs") == [(JOB_DONE,)]

    def test_mark_failed(self, store, db):
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)

        store.mark_failed(delivery, "403 bot was kicked", now=NOW)

        assert rows(db, "SELECT status, attempts FROM notification_deliveries") == [
            (DELIVERY_FAILED, 1)
        ]
        assert store.due_deliveries(now=NOW + timedelta(days=2)) == []

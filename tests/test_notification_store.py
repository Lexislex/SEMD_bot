import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest

from services.notification_store import (
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    JOB_DONE,
    JOB_READY,
    LAST_ATTEMPT_MARGIN,
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

    @pytest.mark.parametrize(
        "trigger_sql, error",
        [
            # нарушение данных — не «версия уже известна», ошибка должна быть видна
            (None, sqlite3.IntegrityError),
            # ошибка БД посреди транзакции (RAISE(FAIL) даёт IntegrityError,
            # подкласс DatabaseError) — без задания на версию это не дубль
            ("SELECT RAISE(FAIL, 'boom')", sqlite3.DatabaseError),
        ],
    )
    def test_failure_rolls_back_passport(self, store, db, trigger_sql, error):
        # если задание не записалось, паспорт тоже не должен остаться —
        # иначе следующий цикл не увидит обновление
        chats = [10]
        if trigger_sql:
            with sqlite3.connect(db) as con:
                con.execute(
                    "CREATE TRIGGER boom BEFORE INSERT ON notification_deliveries "
                    f"BEGIN {trigger_sql}; END"
                )
        else:
            chats = [10, None]  # NOT NULL на последней вставке транзакции

        with pytest.raises(error):
            store.create_job(INFO, "text", chats, now=NOW)

        assert rows(db, "SELECT * FROM nsi_passport") == []
        assert rows(db, "SELECT * FROM notification_jobs") == []

    def test_losing_writer_rolls_back_its_passport(self, store, db):
        # моделирует исход гонки (не саму синхронную гонку потоков): задание на
        # версию уже есть, а паспорта этот writer не видит — его вставка откатывается
        other = NotificationStore(db)
        other.create_job(INFO, "text", [10], now=NOW)
        with sqlite3.connect(db) as con:
            con.execute("DELETE FROM nsi_passport")

        assert store.create_job(INFO, "text", [10], now=NOW) is None

        assert rows(db, "SELECT * FROM nsi_passport") == []
        assert len(rows(db, "SELECT * FROM notification_jobs")) == 1

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

    def test_late_error_with_long_backoff_keeps_trying_until_expiry(self, store):
        # 5 неудач уже дают паузу 6 ч; ошибка в возрасте 19 ч не должна
        # закрывать доставку раньше 24 ч
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)
        delivery = replace(delivery, attempts=5)
        late = NOW + timedelta(hours=19)

        assert store.mark_retry(delivery, "502", now=late)

        last_chance = NOW + MAX_DELIVERY_AGE - LAST_ATTEMPT_MARGIN
        assert store.due_deliveries(now=last_chance - timedelta(seconds=1)) == []
        (due,) = store.due_deliveries(now=last_chance)
        assert not store.is_expired(due, now=last_chance)

    def test_retry_after_is_not_shortened_near_expiry(self, store):
        # 429 в 23:57 с retry_after=120: раньше 23:59 повторять нельзя,
        # хотя «последний шанс» своего backoff — 23:58
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)
        at = NOW + MAX_DELIVERY_AGE - timedelta(minutes=3)

        assert store.mark_retry(
            delivery, "429", now=at, retry_after=timedelta(seconds=120)
        )

        assert store.due_deliveries(now=at + timedelta(minutes=1)) == []
        (due,) = store.due_deliveries(now=at + timedelta(minutes=2))
        assert not store.is_expired(due, now=at + timedelta(minutes=2))

    def test_retry_after_past_expiry_only_expires(self, store):
        # 429 в 23:59 с retry_after=120: до истечения повторов нет,
        # на границе строка всплывает только чтобы закрыться без отправки
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)
        at = NOW + MAX_DELIVERY_AGE - timedelta(minutes=1)

        assert store.mark_retry(
            delivery, "429", now=at, retry_after=timedelta(seconds=120)
        )

        expiry = NOW + MAX_DELIVERY_AGE
        assert store.due_deliveries(now=expiry - timedelta(seconds=1)) == []
        (due,) = store.due_deliveries(now=expiry)
        assert store.is_expired(due, now=expiry)

    def test_gives_up_after_max_age(self, store, db):
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)
        late = NOW + MAX_DELIVERY_AGE

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


class TestExpiryAndMigration:
    def test_pending_after_restart_expires_before_send(self, db):
        # бот лежал больше суток: старое уведомление не отправляется
        NotificationStore(db).create_job(INFO, "text", [10], now=NOW)
        restarted = NotificationStore(db)
        (delivery,) = restarted.due_deliveries(now=NOW + timedelta(days=2))

        assert restarted.is_expired(delivery, now=NOW + timedelta(days=2))
        restarted.mark_expired(delivery, now=NOW + timedelta(days=2))

        assert rows(db, "SELECT status FROM notification_deliveries") == [
            (DELIVERY_FAILED,)
        ]
        assert rows(db, "SELECT status FROM notification_jobs") == [(JOB_DONE,)]

    def test_migrate_chat_retargets_and_is_due(self, store, db):
        store.create_job(INFO, "text", [10], now=NOW)
        (delivery,) = store.due_deliveries(now=NOW)

        assert store.migrate_chat(delivery, -100123, now=NOW)

        (due,) = store.due_deliveries(now=NOW)
        assert due.chat_id == -100123

    def test_migrate_chat_to_existing_recipient_closes_duplicate(self, store, db):
        store.create_job(INFO, "text", [10, -100123], now=NOW)
        old, _ = store.due_deliveries(now=NOW)

        assert not store.migrate_chat(old, -100123, now=NOW)

        assert [d.chat_id for d in store.due_deliveries(now=NOW)] == [-100123]

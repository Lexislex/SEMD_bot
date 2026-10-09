"""Annotation of dictionary 1520 on recorded FNSI responses (tests/fixtures/fnsi_1520.json)."""

import copy
import json
from pathlib import Path

import pytest

from plugins.nsi_update_checker.annotation_1520 import (
    AnnotationUnavailable,
    _oid_list,
    build_1520_annotation,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "fnsi_1520.json").read_text(encoding="utf-8")
)


def fixture_key(endpoint: str, params: dict) -> str:
    return endpoint + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))


class FakeApi:
    """Answers from recorded responses; ``patch`` edits a deep copy per test."""

    def __init__(self, patch=None):
        self.data = copy.deepcopy(FIXTURE)
        self.calls = []
        if patch:
            patch(self.data)

    def get(self, endpoint, **params):
        self.calls.append((endpoint, params))
        return copy.deepcopy(self.data[fixture_key(endpoint, params)])


def compare_key(data: dict, date1: str) -> str:
    return next(k for k in data if k.startswith(f"compare?date1={date1}"))


def build(version: str, api: FakeApi = None, max_chars: int = 3500):
    return build_1520_annotation((api or FakeApi()).get, version, max_chars)


class TestRealReleases:
    def test_new_records(self):
        annotation = build("12.96")

        assert annotation.predecessor == "12.95"
        assert (
            "➕ <b>Добавлены записи СЭМД (3), начало регистрации 10.12.2026:</b>"
            in annotation.html
        )
        assert "<b>325</b> Извещение об установлении диагноза" in annotation.html
        assert "(CDA) ред. 1" in annotation.html and "Редакция" not in annotation.html

    def test_guides_added(self):
        html = build("12.95").html

        assert html.startswith(
            "📘 <b>Добавлены ссылки на руководства по реализации:</b>"
        )
        assert (
            "<a href='https://portal.egisz.rosminzdrav.ru/materials/5284'>340</a>"
            in html
        )
        assert "дата" not in html.lower()  # no false date change (formats differ)

    def test_start_date_moved(self):
        html = build("12.94").html

        assert (
            "📅 <b>Дата начала регистрации перенесена с 10.11.2026 на 01.09.2026:</b> 340–344"
            in html
        )
        assert "<b>339</b>" in html

    def test_end_date_set_new_record_and_guides(self):
        html = build("12.65").html

        lines = html.splitlines()
        assert lines[0].startswith("➕")  # priority: new records first
        assert (
            "📅 <b>Установлена дата окончания регистрации 01.02.2025:</b> 65, 78, 86, 146"
            in html
        )
        assert "📘 <b>Добавлены ссылки на руководства по реализации:</b>" in html

    def test_field_without_event_is_stated_not_dropped(self):
        html = build("12.71").html

        assert html == (
            "ℹ️ <b>Также изменены другие поля:</b> «Доступен на ЕПГУ» — "
            "44, 81, 85, 87, 89, 129, 169, 175, 185, 205, 228, 248, 253"
        )

    def test_one_data_request_per_update_from_predecessor(self):
        api = FakeApi()
        build("12.95", api)

        data_calls = [p for e, p in api.calls if e == "data"]
        assert len(data_calls) == 5
        assert {p["version"] for p in data_calls} == {"12.94"}


class TestRefusals:
    """Anything not fully understood disables the annotation for the whole pair."""

    def test_unsupported_operation_next_to_update(self):
        def patch(data):
            rows = data[compare_key(data, "2026-08-06")]["data"]["list"]
            rows[0]["operation"] = "DELETE"

        with pytest.raises(AnnotationUnavailable, match="unsupported operations"):
            build("12.95", FakeApi(patch))

    def test_changed_field_set(self):
        def patch(data):
            rows = data[compare_key(data, "2026-08-06")]["data"]["list"]
            rows[0]["NEW_COLUMN"] = "x"

        with pytest.raises(AnnotationUnavailable, match="field set differs"):
            build("12.95", FakeApi(patch))

    def test_missing_old_row(self):
        def patch(data):
            data["data?filters=OID|340|EQ&page=1&size=2&version=12.94"]["list"] = []

        with pytest.raises(AnnotationUnavailable, match="340 in 12.94: 0 rows"):
            build("12.95", FakeApi(patch))

    def test_equal_publish_dates(self):
        def patch(data):
            versions = data["versions?page=1&size=50"]["list"]
            versions[1]["publishDate"] = versions[0]["publishDate"]

        with pytest.raises(AnnotationUnavailable, match="ambiguous publish dates"):
            build("12.96", FakeApi(patch))

    def test_empty_compare_is_not_a_complete_diff(self):
        def patch(data):
            data[compare_key(data, "2026-08-10")]["data"] = {"total": None, "list": []}

        with pytest.raises(AnnotationUnavailable, match="no records"):
            build("12.96", FakeApi(patch))

    def test_incomplete_compare(self):
        def patch(data):
            data[compare_key(data, "2026-08-10")]["data"]["total"] = 4

        with pytest.raises(AnnotationUnavailable, match="incomplete"):
            build("12.96", FakeApi(patch))

    def test_missing_data_list(self):
        def patch(data):
            data[compare_key(data, "2026-08-10")]["data"] = None

        with pytest.raises(AnnotationUnavailable, match="no data.list"):
            build("12.96", FakeApi(patch))

    def test_unknown_date_format(self):
        def patch(data):
            rows = data[compare_key(data, "2026-07-31")]["data"]["list"]
            next(r for r in rows if r["OID"] == "340")["START_DATE"] = "1 сентября 2026"

        with pytest.raises(AnnotationUnavailable, match="unknown date format"):
            build("12.94", FakeApi(patch))

    def test_duplicate_key(self):
        def patch(data):
            rows = data[compare_key(data, "2026-08-10")]["data"]["list"]
            rows[1]["OID"] = rows[0]["OID"]

        with pytest.raises(AnnotationUnavailable, match="not unique"):
            build("12.96", FakeApi(patch))

    def test_version_not_listed(self):
        with pytest.raises(AnnotationUnavailable, match="not in /versions"):
            build("99.99")


class TestRendering:
    def test_lists_shrink_to_fit(self):
        full = build("12.96").html
        short = build("12.96", max_chars=len(full) - 50).html

        assert len(short) < len(full)
        assert "…и ещё" in short

    def test_too_small_room_refuses(self):
        with pytest.raises(AnnotationUnavailable, match="does not fit"):
            build("12.96", max_chars=40)

    def test_names_are_escaped(self):
        def patch(data):
            rows = data[compare_key(data, "2026-08-10")]["data"]["list"]
            rows[0]["NAME"] = "Заключение <b>&</b> справка (CDA) Редакция 1"

        html = build("12.96", FakeApi(patch)).html
        assert "Заключение &lt;b&gt;&amp;&lt;/b&gt; справка (CDA) ред. 1" in html

    @pytest.mark.parametrize(
        "oids, expected",
        [
            (["344", "340", "341", "342", "343"], "340–344"),
            (["1", "2", "5"], "1, 2, 5"),
            (["65", "78", "86", "146"], "65, 78, 86, 146"),
            (["7"], "7"),
        ],
    )
    def test_oid_list(self, oids, expected):
        assert _oid_list(oids) == expected

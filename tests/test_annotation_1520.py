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


class TestCompletenessChecks:
    """Codex review of #25: refusals that must not let a partial diff through."""

    def test_non_empty_compare_without_total(self):
        def patch(data):
            payload = data[compare_key(data, "2026-08-10")]["data"]
            payload["list"].pop()
            payload["total"] = None

        with pytest.raises(AnnotationUnavailable, match="no numeric total"):
            build("12.96", FakeApi(patch))

    def test_total_changes_between_pages(self):
        from plugins.nsi_update_checker import annotation_1520 as module

        api = FakeApi()
        key = compare_key(api.data, "2026-08-10")
        rows = api.data[key]["data"]["list"]
        pages = {1: {"total": 3, "list": rows[:2]}, 2: {"total": 4, "list": rows[2:]}}
        original = api.get

        def get(endpoint, **params):
            if endpoint == "compare":
                return {"result": "OK", "data": pages[params["page"]]}
            return original(endpoint, **params)

        with patch_page_size(module, 2):
            with pytest.raises(AnnotationUnavailable, match="total changed"):
                build_1520_annotation(get, "12.96", 3500)

    def test_multi_page_compare_is_collected(self):
        from plugins.nsi_update_checker import annotation_1520 as module

        api = FakeApi()
        key = compare_key(api.data, "2026-08-10")
        rows = api.data[key]["data"]["list"]
        pages = {1: {"total": 3, "list": rows[:2]}, 2: {"total": 3, "list": rows[2:]}}
        original = api.get

        def get(endpoint, **params):
            if endpoint == "compare":
                return {"result": "OK", "data": pages[params["page"]]}
            return original(endpoint, **params)

        with patch_page_size(module, 2):
            html = build_1520_annotation(get, "12.96", 3500).html
        assert "Добавлены записи СЭМД (3)" in html

    @pytest.mark.parametrize(
        "edit, match",
        [
            (
                lambda resp: resp["list"][0].__setitem__(
                    [i for i, c in enumerate(resp["list"][0]) if c["column"] == "OID"][
                        0
                    ],
                    {"column": "OID", "value": "999"},
                ),
                "got a row of OID",
            ),
            (lambda resp: resp.__setitem__("total", 2), "1 rows"),
            (
                lambda resp: resp["list"][0].append({"column": "NAME", "value": "x"}),
                "duplicate columns",
            ),
        ],
    )
    def test_old_row_must_be_the_requested_record(self, edit, match):
        def patch(data):
            edit(data["data?filters=OID|340|EQ&page=1&size=2&version=12.94"])

        with pytest.raises(AnnotationUnavailable, match=match):
            build("12.95", FakeApi(patch))

    def test_newer_release_in_same_minute(self):
        def patch(data):
            versions = data["versions?page=1&size=50"]["list"]
            versions.insert(0, dict(versions[0], version="12.97"))

        with pytest.raises(AnnotationUnavailable, match="12.96→12.97"):
            build("12.96", FakeApi(patch))

    @pytest.mark.parametrize(
        "version, notes",
        [
            (
                "12.96",
                "Добавлено записей: 3;\nИзменено записей: 0;\nУдалено записей: 0;\nДобавлено полей: 0;\nИзменено полей: 0;\nУдалено полей: 0;",
            ),
            (
                "12.95",
                "Добавлено записей: 0;\nИзменено записей: 5;\nУдалено записей: 0;",
            ),
            (
                "12.94",
                "Добавлено записей: 1;\nИзменено записей: 5;\nУдалено записей: 0;",
            ),
        ],
    )
    def test_matching_release_counters(self, version, notes):
        build_1520_annotation(FakeApi().get, version, 3500, release_notes=notes)

    @pytest.mark.parametrize(
        "notes, match",
        [
            (
                "Добавлено записей: 4;\nИзменено записей: 0;\nУдалено записей: 0;",
                "differ from compare",
            ),
            (
                "Добавлено записей: 3;\nИзменено записей: 0;\nУдалено записей: 1;",
                "differ from compare",
            ),
            (
                "Добавлено записей: 3;\nИзменено записей: 0;\nУдалено записей: 0;\nДобавлено полей: 1;",
                "schema changed",
            ),
        ],
    )
    def test_release_counters_mismatch(self, notes, match):
        with pytest.raises(AnnotationUnavailable, match=match):
            build_1520_annotation(FakeApi().get, "12.96", 3500, release_notes=notes)

    def test_unparsable_counters_skip_the_check(self):
        build_1520_annotation(
            FakeApi().get, "12.96", 3500, release_notes="<p>описание</p>"
        )


class patch_page_size:
    def __init__(self, module, size):
        self.module, self.size = module, size

    def __enter__(self):
        self.old = self.module.COMPARE_PAGE_SIZE
        self.module.COMPARE_PAGE_SIZE = self.size

    def __exit__(self, *exc):
        self.module.COMPARE_PAGE_SIZE = self.old

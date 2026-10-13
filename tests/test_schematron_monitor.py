import sqlite3
from unittest.mock import MagicMock

import pytest

from plugins.schematron_monitor import monitor as monitor_module
from plugins.schematron_monitor.formatters import (
    build_diff_text,
    diff_file_name,
    diff_stats,
    format_change_message,
    is_night,
    tg_length,
    with_inline_diff,
)
from plugins.schematron_monitor.monitor import (
    MAX_ATTACHED_FILES,
    SCHEMATRON,
    SKIP_DOWNLOAD_FAILED,
    SKIP_LIMIT_EXCEEDED,
    SKIP_LIST_FAILED,
    SKIP_TOO_LARGE,
    XSD,
    NotificationError,
    SchematronMonitor,
    is_schematron_path,
)
from services.gitlab_client import (
    GitLabAuthError,
    GitLabClient,
    GitLabError,
    GitLabNotFoundError,
)
from services.schematron_store import (
    STATUS_ERROR,
    STATUS_NO_FILES,
    STATUS_NO_GIT_LINK,
    STATUS_NO_SCHEMATRON,
    STATUS_NOT_IN_1520,
    STATUS_OK,
    STATUS_REPO_NOT_FOUND,
    SchematronStore,
    WatchState,
)

GIT_LINK = "1.2.643.5.1.13.13.15.33.4"
SEMD = {
    "OID": "331",
    "NAME": "Направление на госпитализацию (CDA) Редакция 4",
    "GIT_LINK": GIT_LINK,
}

SCH_DIFF = {
    "old_path": "schematron/331 Schematron v1.2.sch",
    "new_path": "schematron/331 Schematron v1.3.sch",
    "diff": '@@ -1,3 +1,3 @@\n <pattern>\n-<assert test="a"/>\n+<assert test="b"/>\n',
    "new_file": False,
    "renamed_file": True,
    "deleted_file": False,
}
DOCX_DIFF = {
    "old_path": "guide/Пояснения.docx",
    "new_path": "guide/Пояснения.docx",
    "diff": "Binary files differ",
    "new_file": False,
    "renamed_file": False,
    "deleted_file": False,
}


def commit(sha: str, title: str = "Обновление файла схематрона") -> dict:
    return {
        "id": sha * 5,
        "short_id": sha,
        "title": title,
        "author_name": "Автор",
        "committed_date": "2026-09-07T11:46:40.000+00:00",
    }


@pytest.fixture
def store(tmp_path) -> SchematronStore:
    return SchematronStore(tmp_path / "fnsi.sqlite")


@pytest.fixture
def client() -> MagicMock:
    real = GitLabClient("https://git.example.ru", token="t")
    mock = MagicMock(spec=GitLabClient)
    mock.compare_url.side_effect = real.compare_url
    mock.tree_url.side_effect = real.tree_url
    mock.commit_url.side_effect = real.commit_url
    mock.list_commits.return_value = []
    mock.list_files.return_value = [
        "schematron/.gitkeep",
        "schematron/331 Schematron v1.3.sch",
    ]
    mock.get_raw_file.side_effect = (
        lambda repo, path, ref: f"<schema {path}@{ref}/>".encode()
    )
    return mock


@pytest.fixture
def notify() -> MagicMock:
    return MagicMock()


@pytest.fixture
def monitor(client, store, notify) -> SchematronMonitor:
    lookup = {"331": SEMD, "5": {"OID": "5", "NAME": "Без ссылки", "GIT_LINK": None}}
    return SchematronMonitor(client, store, lookup.get, notify)


def test_is_schematron_path():
    assert is_schematron_path("schematron/331 Schematron v1.3.sch")
    assert is_schematron_path("schematron/sub/x.SCH")
    assert not is_schematron_path("schematron/.gitkeep")
    assert not is_schematron_path("xsl/331_v1.2.xsl")
    assert not is_schematron_path(None)


class TestMonitor:
    def test_first_run_stores_baseline(self, monitor, client, store, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")

        assert monitor.check("331") is None

        state = store.get("331")
        assert state.last_sha == "aaaaaaaa" * 5
        assert state.git_link == f"semd/1.2.643.5.1.13.13.15.33@{GIT_LINK}"
        assert state.status == STATUS_OK
        client.get_last_commit.assert_called_once()
        assert client.get_last_commit.call_args.kwargs["path"] == "schematron"
        client.compare.assert_not_called()
        notify.assert_not_called()

    def test_same_sha_no_compare(self, monitor, client, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        monitor.check("331")
        client.compare.assert_not_called()
        notify.assert_not_called()

    def test_change_without_sch_advances_silently(self, monitor, client, store, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {
            "commits": [commit("bbbbbbbb")],
            "diffs": [DOCX_DIFF],
        }

        assert monitor.check("331") is None

        notify.assert_not_called()
        assert store.get("331").last_sha == "bbbbbbbb" * 5

    def test_schematron_change_notifies(self, monitor, client, store, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {
            "commits": [commit("bbbbbbbb")],
            "diffs": [DOCX_DIFF, SCH_DIFF],
        }

        change = monitor.check("331")

        notify.assert_called_once_with(change)
        assert change.diffs == [SCH_DIFF]
        assert change.from_sha == "aaaaaaaa" * 5
        assert change.to_sha == "bbbbbbbb" * 5
        assert "/-/compare/" in change.compare_url
        state = store.get("331")
        assert state.last_sha == "bbbbbbbb" * 5
        assert state.last_changed == "2026-09-07T11:46:40.000+00:00"

    def test_failed_notify_keeps_baseline(self, monitor, client, store, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {
            "commits": [commit("bbbbbbbb")],
            "diffs": [SCH_DIFF],
        }
        notify.side_effect = RuntimeError("telegram down")

        with pytest.raises(RuntimeError):
            monitor.check("331")

        assert store.get("331").last_sha == "aaaaaaaa" * 5

    def test_history_rewritten(self, monitor, client, store, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("cccccccc")
        client.compare.side_effect = GitLabNotFoundError("404 Ref Not Found")

        change = monitor.check("331")

        assert change.history_rewritten
        assert change.compare_url == ""
        # Сравнения нет — прикладываем текущие .sch целиком (без .gitkeep)
        assert change.attachments == [
            (
                "schematron/331 Schematron v1.3.sch",
                f"<schema schematron/331 Schematron v1.3.sch@{'cccccccc' * 5}/>".encode(),
            )
        ]
        client.list_files.assert_called_once_with(
            change.repo, "schematron", "cccccccc" * 5
        )
        notify.assert_called_once()
        assert store.get("331").last_sha == "cccccccc" * 5

    def test_history_rewritten_download_failure_still_notifies(
        self, monitor, client, notify
    ):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("cccccccc")
        client.compare.side_effect = GitLabNotFoundError("404")
        client.get_raw_file.side_effect = GitLabError("500")

        change = monitor.check("331")

        assert change.attachments == []
        notify.assert_called_once()

    def test_truncated_diff_attaches_new_file(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        big = dict(SCH_DIFF, diff="", too_large=True)
        client.compare.return_value = {"commits": [], "diffs": [big]}

        change = monitor.check("331")

        assert [p for p, _ in change.attachments] == [SCH_DIFF["new_path"]]
        client.list_files.assert_not_called()

    def test_regular_diff_has_no_attachments(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {"commits": [], "diffs": [SCH_DIFF]}

        assert monitor.check("331").attachments == []
        client.get_raw_file.assert_not_called()

    def test_compare_timeout_attaches_current_files(
        self, monitor, client, store, notify
    ):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {
            "commits": [],
            "diffs": [],
            "compare_timeout": True,
        }
        client.list_commits.return_value = [commit("bbbbbbbb")]

        change = monitor.check("331")

        # Раньше пустые diffs при таймауте молча сдвигали baseline
        assert change.compare_timed_out
        assert [p for p, _ in change.attachments] == [
            "schematron/331 Schematron v1.3.sch"
        ]
        notify.assert_called_once_with(change)
        assert store.get("331").last_sha == "bbbbbbbb" * 5

    def test_git_link_changed_resets_baseline(self, monitor, client, store, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        SEMD_NEW = dict(SEMD, GIT_LINK="1.2.643.5.1.13.13.15.33.5")
        monitor.semd_lookup = {"331": SEMD_NEW}.get
        client.get_last_commit.return_value = commit("dddddddd")

        assert monitor.check("331") is None

        client.compare.assert_not_called()
        notify.assert_not_called()
        state = store.get("331")
        assert state.git_link == f"semd/1.2.643.5.1.13.13.15.33@{SEMD_NEW['GIT_LINK']}"
        assert state.last_sha == "dddddddd" * 5

    def test_repo_resolved_via_638(self, monitor, client, store):
        # СЭМД 113: пакет ...15.36.5 лежит в проекте ...15.35
        url = (
            "https://git.minzdrav.gov.ru/semd/1.2.643.5.1.13.13.15.35/-/tree/"
            "1.2.643.5.1.13.13.15.35.5"
        )
        monitor.package_lookup = {GIT_LINK: url}.get
        client.get_last_commit.return_value = commit("aaaaaaaa")

        monitor.check("331")

        repo = client.get_last_commit.call_args.args[0]
        assert repo.project_path == "semd/1.2.643.5.1.13.13.15.35"
        assert repo.ref == "1.2.643.5.1.13.13.15.35.5"
        assert repo.git_link == GIT_LINK
        assert store.get("331").git_link == f"{repo.project_path}@{repo.ref}"

    @pytest.mark.parametrize(
        "lookup",
        [
            {}.get,  # пакета нет в 638
            {GIT_LINK: "https://git.minzdrav.gov.ru/semd/x"}.get,  # битая ссылка
            MagicMock(side_effect=RuntimeError("638 broken")),
        ],
    )
    def test_repo_falls_back_to_heuristic(self, monitor, client, store, lookup):
        monitor.package_lookup = lookup
        client.get_last_commit.return_value = commit("aaaaaaaa")

        monitor.check("331")

        repo = client.get_last_commit.call_args.args[0]
        assert repo.project_path == "semd/1.2.643.5.1.13.13.15.33"
        assert repo.ref == GIT_LINK
        assert store.get("331").status == STATUS_OK

    def test_legacy_raw_git_link_keeps_baseline(self, monitor, client, store):
        # Старые записи хранят OID пакета — та же ветка не должна сбрасывать baseline
        store.save(WatchState(semd_oid="331", git_link=GIT_LINK, last_sha="a" * 40))
        client.get_last_commit.return_value = commit("aaaaaaaa")

        monitor.check("331")

        state = store.get("331")
        assert state.last_sha == "a" * 40
        assert state.git_link == f"semd/1.2.643.5.1.13.13.15.33@{GIT_LINK}"

    def test_remap_in_638_resets_baseline(self, monitor, client, store, notify):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        monitor.package_lookup = {
            GIT_LINK: "https://git.minzdrav.gov.ru/semd/other/-/blob/other.1"
        }.get
        client.get_last_commit.return_value = commit("dddddddd")

        assert monitor.check("331") is None

        client.compare.assert_not_called()
        notify.assert_not_called()
        state = store.get("331")
        assert state.git_link == "semd/other@other.1"
        assert state.last_sha == "dddddddd" * 5

    def test_repo_not_found(self, monitor, client, store):
        client.get_last_commit.side_effect = GitLabNotFoundError("404")
        assert monitor.check("331") is None
        assert store.get("331").status == STATUS_REPO_NOT_FOUND

    def test_no_schematron(self, monitor, client, store):
        client.get_last_commit.return_value = None
        assert monitor.check("331") is None
        assert store.get("331").status == STATUS_NO_SCHEMATRON

    def test_not_in_1520_and_no_git_link(self, monitor, client, store):
        monitor.check("999")
        monitor.check("5")
        assert store.get("999").status == STATUS_NOT_IN_1520
        assert store.get("5").status == STATUS_NO_GIT_LINK
        client.get_last_commit.assert_not_called()

    def test_check_all_stops_on_auth_error(self, monitor, client):
        client.get_last_commit.side_effect = GitLabAuthError("401")
        monitor.check_all(["331", "331"])
        assert client.get_last_commit.call_count == 1

    def test_check_all_notification_error_keeps_baseline_and_continues(
        self, monitor, client, store, notify
    ):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {"commits": [], "diffs": [SCH_DIFF]}
        notify.side_effect = NotificationError("no chats")

        assert monitor.check_all(["331", "5"]) == []

        assert store.get("331").last_sha == "aaaaaaaa" * 5
        assert store.get("5").status == STATUS_NO_GIT_LINK  # цикл продолжился

    def test_check_all_continues_after_error(self, monitor, client, store):
        calls = []

        def last_commit(repo, path):
            calls.append(path)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return commit("aaaaaaaa")

        client.get_last_commit.side_effect = last_commit
        monitor.check_all(["331", "331"])
        assert store.get("331").last_sha == "aaaaaaaa" * 5
        assert store.get("331", "xsd").last_sha == "aaaaaaaa" * 5

    def test_commits_filtered_to_schematron(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {
            "commits": [commit("readme00", "README"), commit("bbbbbbbb")],
            "diffs": [SCH_DIFF],
        }
        client.list_commits.return_value = [commit("bbbbbbbb")]

        change = monitor.check("331")

        assert [c["short_id"] for c in change.commits] == ["bbbbbbbb"]
        assert client.list_commits.call_args.kwargs["path"] == "schematron"

    def test_commits_fallback_to_compare(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {
            "commits": [commit("old00000"), commit("bbbbbbbb")],
            "diffs": [SCH_DIFF],
        }
        client.list_commits.side_effect = GitLabError("500")

        change = monitor.check("331")

        # compare отдаёт от старых к новым, в change — свежие первыми
        assert [c["short_id"] for c in change.commits] == ["bbbbbbbb", "old00000"]


class TestFormatters:
    @pytest.fixture
    def change(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {
            "commits": [commit("bbbbbbbb")],
            "diffs": [SCH_DIFF],
        }
        return monitor.check("331")

    def test_diff_stats(self):
        assert diff_stats(SCH_DIFF["diff"]) == (1, 1)
        assert diff_stats("--- a/x\n+++ b/x\n+new\n") == (1, 0)

    def test_message(self, change, client):
        text = format_change_message(change, client)
        assert "Изменён схематрон" in text
        assert "<code>331</code>" in text
        assert (
            "schematron/331 Schematron v1.2.sch → schematron/331 Schematron v1.3.sch"
            in text
        )
        assert "(+1 / −1)" in text
        assert "/-/compare/" in text
        assert text.endswith("#схематрон #СЭМД_331")
        assert "Автор" not in text

    def test_inline_diff_before_hashtags(self, change, client):
        text = with_inline_diff(format_change_message(change, client), change)
        # <pre> внутри свёрнутой цитаты мобильные клиенты не сворачивают
        assert "<blockquote expandable><code>" in text
        assert "<pre>" not in text
        assert "&lt;assert test=&quot;b&quot;/&gt;" in text
        assert text.index("<blockquote") < text.index("#схематрон")

    def test_inline_diff_skipped_when_long(self, change, client):
        change.diffs = [dict(SCH_DIFF, diff="+x\n" * 2000)]
        message = format_change_message(change, client)
        assert with_inline_diff(message, change) == message

    def test_message_truncated_with_attachment(self, change, client):
        change.diffs = [dict(SCH_DIFF, diff="", too_large=True)]
        change.attachments = [(SCH_DIFF["new_path"], b"x")]
        text = format_change_message(change, client)
        assert "новая версия приложена файлом" in text
        assert with_inline_diff(text, change) == text

    def test_message_history_rewritten_mentions_attachment(self, change, client):
        change.history_rewritten = True
        change.attachments = [(SCH_DIFF["new_path"], b"x")]
        text = format_change_message(change, client)
        assert "сравнение недоступно" in text
        assert "приложена файлом" in text

    def test_message_fits_telegram_limit_with_many_files(self, change, client):
        change.diffs = [
            dict(SCH_DIFF, new_path=f"schematron/{'очень длинное имя ' * 5}{i}.sch")
            for i in range(300)
        ]
        text = format_change_message(change, client)
        assert tg_length(text) <= 4000
        assert "…и ещё" in text
        assert text.endswith("#схематрон #СЭМД_331")

    def test_message_escapes_gitlab_data(self, change, client):
        change.semd_name = "<b>name</b>"
        change.diffs = [
            dict(SCH_DIFF, new_path="schematron/<script>.sch", renamed_file=False)
        ]
        change.commits = [dict(commit("bbbbbbbb"), title="<a href='x'>evil</a> & co")]
        text = format_change_message(change, client)
        assert "<script>" not in text and "&lt;script&gt;" in text
        assert "<a href='x'>" not in text
        assert "&lt;a href=&#x27;x&#x27;&gt;evil&lt;/a&gt; &amp; co" in text
        assert "&lt;b&gt;name&lt;/b&gt;" in text

    def test_message_compare_timeout(self, change, client):
        change.compare_timed_out = True
        change.diffs = []
        change.attachments = [(SCH_DIFF["new_path"], b"x")]
        text = format_change_message(change, client)
        assert "не успел построить сравнение" in text
        assert "приложена файлом" in text
        assert "bbbbbbbb" in text  # коммит показан
        assert with_inline_diff(text, change) == text

    def test_diff_file(self, change):
        text = build_diff_text(change)
        assert "--- a/schematron/331 Schematron v1.2.sch" in text
        assert "+++ b/schematron/331 Schematron v1.3.sch" in text
        assert '+<assert test="b"/>' in text

    def test_is_night(self):
        assert is_night(23) and is_night(3)
        assert not is_night(8) and not is_night(21)


XSD_DIFF = {
    "old_path": "xsd/SEMD_P6/STRUCTURED_BODY.xsd",
    "new_path": "xsd/SEMD_P6/STRUCTURED_BODY.xsd",
    "diff": '@@ -1 +1 @@\n-<xsd:attribute use="required"/>\n+<xsd:attribute use="optional"/>\n',
    "new_file": False,
    "renamed_file": False,
    "deleted_file": False,
}


def by_kind(sch: str, xsd: str):
    """get_last_commit side effect: separate head per kind directory."""
    heads = {"schematron": sch, "xsd": xsd}

    def last_commit(repo, path):
        return commit(heads[path])

    return last_commit


def compare_by_target(diffs_by_sha: dict):
    """compare side effect: diffs depend on the target sha (= kind)."""

    def compare(repo, from_sha, to_sha):
        return {"commits": [], "diffs": diffs_by_sha[to_sha[:8]]}

    return compare


class TestKinds:
    def test_kind_paths(self):
        assert XSD.matches_path("xsd/XSD CDA/coreschemas/voc.xsd")
        assert XSD.matches_path("xsd/a/B.XSD")
        assert not XSD.matches_path("xsd/.gitkeep")
        assert not XSD.matches_path("schematron/x.sch")
        assert not SCHEMATRON.matches_path("xsd/a.xsd")
        assert XSD.matches_diff({"old_path": "xsd/a.xsd", "new_path": "other/a.xsd"})

    def test_first_run_sets_both_baselines(self, monitor, client, store, notify):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")

        assert monitor.check_all(["331"]) == []

        assert store.get("331").last_sha == "aaaaaaaa" * 5
        assert store.get("331", "xsd").last_sha == "cccccccc" * 5
        paths = [c.kwargs["path"] for c in client.get_last_commit.call_args_list]
        assert paths == ["schematron", "xsd"]
        notify.assert_not_called()

    def test_xsd_change_notifies_with_xsd_kind(self, monitor, client, store, notify):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor.check_all(["331"])
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "dddddddd")
        client.compare.return_value = {"commits": [], "diffs": [XSD_DIFF, SCH_DIFF]}

        changes = monitor.check_all(["331"])

        assert len(changes) == 1
        change = changes[0]
        assert change.kind is XSD
        assert change.diffs == [XSD_DIFF]
        assert change.tree_url.endswith("/xsd")
        assert client.list_commits.call_args.kwargs["path"] == "xsd"
        assert store.get("331", "xsd").last_sha == "dddddddd" * 5
        assert store.get("331").last_sha == "aaaaaaaa" * 5

    def test_sch_only_commit_does_not_trigger_xsd(self, monitor, client, store, notify):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor.check_all(["331"])
        # XSD-голова сдвинулась, но в диапазоне только .sch
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "dddddddd")
        client.compare.return_value = {"commits": [], "diffs": [SCH_DIFF]}

        assert monitor.check_all(["331"]) == []
        notify.assert_not_called()
        assert store.get("331", "xsd").last_sha == "dddddddd" * 5

    def test_both_kinds_changed_two_deliveries(self, monitor, client, notify):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor.check_all(["331"])
        client.get_last_commit.side_effect = by_kind("bbbbbbbb", "dddddddd")
        client.compare.side_effect = compare_by_target(
            {"bbbbbbbb": [SCH_DIFF], "dddddddd": [XSD_DIFF]}
        )

        changes = monitor.check_all(["331"])

        assert [c.kind for c in changes] == [SCHEMATRON, XSD]
        assert notify.call_count == 2

    @pytest.mark.parametrize(
        "error", [NotificationError("no chats"), RuntimeError("boom")]
    )
    def test_xsd_failure_keeps_schematron_result(
        self, monitor, client, store, notify, error
    ):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor.check_all(["331"])
        client.get_last_commit.side_effect = by_kind("bbbbbbbb", "dddddddd")
        client.compare.side_effect = compare_by_target(
            {"bbbbbbbb": [SCH_DIFF], "dddddddd": [XSD_DIFF]}
        )
        notify.side_effect = [None, error]

        changes = monitor.check_all(["331"])

        assert [c.kind for c in changes] == [SCHEMATRON]
        assert store.get("331").last_sha == "bbbbbbbb" * 5
        assert store.get("331", "xsd").last_sha == "cccccccc" * 5

    def test_schematron_failure_does_not_block_xsd(
        self, monitor, client, store, notify
    ):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor.check_all(["331"])
        client.get_last_commit.side_effect = by_kind("bbbbbbbb", "dddddddd")
        client.compare.side_effect = compare_by_target(
            {"bbbbbbbb": [SCH_DIFF], "dddddddd": [XSD_DIFF]}
        )
        notify.side_effect = [NotificationError("down"), None]

        changes = monitor.check_all(["331"])

        assert [c.kind for c in changes] == [XSD]
        assert store.get("331").last_sha == "aaaaaaaa" * 5
        assert store.get("331", "xsd").last_sha == "dddddddd" * 5

    def test_auth_error_on_xsd_returns_delivered_and_stops(
        self, monitor, client, store, notify
    ):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor.check_all(["331"])
        heads = by_kind("bbbbbbbb", "dddddddd")

        def last_commit(repo, path):
            if path == "xsd":
                raise GitLabAuthError("401")
            return heads(repo, path)

        client.get_last_commit.side_effect = last_commit
        client.get_last_commit.reset_mock()
        client.compare.return_value = {"commits": [], "diffs": [SCH_DIFF]}

        changes = monitor.check_all(["331", "331"])

        assert [c.kind for c in changes] == [SCHEMATRON]
        assert store.get("331").last_sha == "bbbbbbbb" * 5
        assert client.get_last_commit.call_count == 2  # второй OID не проверялся

    def test_check_single_kind_raises_notification_error(self, monitor, client, notify):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor.check("331", XSD)
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "dddddddd")
        client.compare.return_value = {"commits": [], "diffs": [XSD_DIFF]}
        notify.side_effect = NotificationError("no chats")

        with pytest.raises(NotificationError):
            monitor.check("331", XSD)

    def test_lookup_errors_saved_for_both_kinds(self, monitor, client, store):
        store.save(WatchState(semd_oid="5", last_sha="s" * 40, kind="xsd"))

        monitor.check_all(["404", "5"])

        assert store.get("404").status == STATUS_NOT_IN_1520
        assert store.get("404", "xsd").status == STATUS_NOT_IN_1520
        assert store.get("5", "xsd").status == STATUS_NO_GIT_LINK
        assert store.get("5", "xsd").last_sha == "s" * 40  # baseline сохранён
        client.get_last_commit.assert_not_called()

    def test_repo_change_resets_both_baselines(self, monitor, client, store, notify):
        for kind in ("schematron", "xsd"):
            store.save(
                WatchState(
                    semd_oid="331", git_link="semd/old@1", last_sha="o" * 40, kind=kind
                )
            )
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")

        assert monitor.check_all(["331"]) == []

        assert store.get("331").last_sha == "aaaaaaaa" * 5
        assert store.get("331", "xsd").last_sha == "cccccccc" * 5
        client.compare.assert_not_called()

    def test_no_xsd_files_status(self, monitor, client, store):
        def last_commit(repo, path):
            return commit("aaaaaaaa") if path == "schematron" else None

        client.get_last_commit.side_effect = last_commit
        monitor.check_all(["331"])

        assert store.get("331").status == STATUS_OK
        assert store.get("331", "xsd").status == STATUS_NO_FILES


class TestAttachments:
    def _rewritten(self, monitor, client, files):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331", XSD)
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.side_effect = GitLabNotFoundError("404")
        client.list_files.return_value = files
        return monitor.check("331", XSD)

    def test_limit_allows_exactly_max(self, monitor, client):
        files = [f"xsd/f{i}.xsd" for i in range(MAX_ATTACHED_FILES)]
        change = self._rewritten(monitor, client, files + ["xsd/.gitkeep"])

        assert [p for p, _ in change.attachments] == files
        assert change.skipped == []

    def test_limit_exceeded_downloads_nothing(self, monitor, client):
        files = [f"xsd/f{i}.xsd" for i in range(MAX_ATTACHED_FILES + 1)]
        change = self._rewritten(monitor, client, files)

        client.get_raw_file.assert_not_called()
        assert change.attachments == []
        assert change.skipped == [(p, SKIP_LIMIT_EXCEEDED) for p in files]

    def test_limit_applies_to_truncated_compare(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331", XSD)
        client.get_last_commit.return_value = commit("bbbbbbbb")
        diffs = [
            dict(
                XSD_DIFF,
                new_path=f"xsd/f{i}.xsd",
                old_path=f"xsd/f{i}.xsd",
                too_large=True,
            )
            for i in range(MAX_ATTACHED_FILES + 1)
        ]
        client.compare.return_value = {"commits": [], "diffs": diffs}

        change = monitor.check("331", XSD)

        client.get_raw_file.assert_not_called()
        assert len(change.skipped) == MAX_ATTACHED_FILES + 1

    def test_failed_and_too_large_are_skipped(self, monitor, client, monkeypatch):
        monkeypatch.setattr(monitor_module, "MAX_DOCUMENT_BYTES", 10)

        def raw(repo, path, ref):
            if path.endswith("broken.xsd"):
                raise GitLabError("500")
            return b"x" * (100 if path.endswith("big.xsd") else 5)

        client.get_raw_file.side_effect = raw
        change = self._rewritten(
            monitor, client, ["xsd/ok.xsd", "xsd/broken.xsd", "xsd/big.xsd"]
        )

        assert [p for p, _ in change.attachments] == ["xsd/ok.xsd"]
        assert change.skipped == [
            ("xsd/broken.xsd", SKIP_DOWNLOAD_FAILED),
            ("xsd/big.xsd", SKIP_TOO_LARGE),
        ]

    def test_rename_out_of_kind_dir_not_downloaded(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331", XSD)
        client.get_last_commit.return_value = commit("bbbbbbbb")
        moved = dict(
            XSD_DIFF, old_path="xsd/a.xsd", new_path="old/a.xsd", too_large=True
        )
        client.compare.return_value = {"commits": [], "diffs": [moved]}

        change = monitor.check("331", XSD)

        assert change.diffs == [moved]
        client.get_raw_file.assert_not_called()


class TestKindFormatting:
    def _change(self, monitor, client, **kwargs):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331", XSD)
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {"commits": [], "diffs": [XSD_DIFF]}
        change = monitor.check("331", XSD)
        for key, value in kwargs.items():
            setattr(change, key, value)
        return change

    def test_xsd_message(self, monitor, client):
        change = self._change(monitor, client)
        text = format_change_message(change, client)

        assert text.startswith("📐 <b>Изменена XSD-схема СЭМД</b>")
        assert "Папка xsd" in text
        assert text.endswith("#XSD #СЭМД_331")
        assert diff_file_name(change).startswith("xsd_331_")

    def test_schematron_diff_name_unchanged(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.return_value = {"commits": [], "diffs": [SCH_DIFF]}
        change = monitor.check("331")

        assert diff_file_name(change) == "schematron_331_aaaaaaaa_bbbbbbbb.diff"

    @pytest.mark.parametrize(
        "attachments, skipped, expected",
        [
            ([("xsd/a.xsd", b"x")], [], "Текущая версия XSD-схемы приложена файлом"),
            ([], [("xsd/a.xsd", SKIP_LIMIT_EXCEEDED)], "Файлов слишком много (1)"),
            (
                [("xsd/a.xsd", b"x")],
                [("xsd/b.xsd", SKIP_TOO_LARGE)],
                "Приложено файлов: 1; часть файлов недоступна",
            ),
            (
                [],
                [("xsd/b.xsd", SKIP_DOWNLOAD_FAILED)],
                "Файлы не приложены (недоступны или превышают лимит)",
            ),
        ],
    )
    def test_attachment_note_matches_reality(
        self, monitor, client, attachments, skipped, expected
    ):
        change = self._change(
            monitor,
            client,
            history_rewritten=True,
            attachments=attachments,
            skipped=skipped,
        )
        text = format_change_message(change, client)

        assert expected in text
        if not attachments:
            assert "приложена файлом" not in text


class TestStoreKinds:
    def test_kinds_are_independent(self, store):
        store.save(WatchState(semd_oid="1", last_sha="s" * 40))
        store.save(WatchState(semd_oid="1", last_sha="x" * 40, kind="xsd"))

        # Старые вызовы без kind видят только схематрон
        assert store.get("1").last_sha == "s" * 40
        assert store.get("1").kind == "schematron"
        assert {k: v.last_sha for k, v in store.get_all().items()} == {"1": "s" * 40}
        assert store.get("1", "xsd").last_sha == "x" * 40
        assert store.get_all("xsd")["1"].kind == "xsd"

    def test_existing_schematron_rows_untouched(self, tmp_path):
        db = tmp_path / "old.sqlite"
        con = sqlite3.connect(db)
        con.execute(
            "CREATE TABLE schematron_watch (semd_oid TEXT PRIMARY KEY, git_link TEXT,"
            " last_sha TEXT, status TEXT, last_checked TEXT, last_changed TEXT)"
        )
        con.execute(
            "INSERT INTO schematron_watch VALUES ('289', 'semd/x@y', 'abc', 'ok', 't', NULL)"
        )
        con.commit()
        con.close()

        store = SchematronStore(db)

        assert store.get("289") == WatchState("289", "semd/x@y", "abc", "ok", "t", None)
        assert store.get("289", "xsd") is None

    def test_unknown_kind_rejected(self, store):
        with pytest.raises(ValueError):
            store.get("1", "xsd_watch; DROP TABLE x")


class TestReviewFixes:
    def _truncated_change(self, monitor, client, count):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331", XSD)
        client.get_last_commit.return_value = commit("bbbbbbbb")
        diffs = [
            dict(
                XSD_DIFF,
                new_path=f"xsd/f{i}.xsd",
                old_path=f"xsd/f{i}.xsd",
                too_large=True,
            )
            for i in range(count)
        ]
        client.compare.return_value = {"commits": [], "diffs": diffs}
        return monitor.check("331", XSD)

    def test_regular_compare_reports_limit_exceeded(self, monitor, client):
        change = self._truncated_change(monitor, client, MAX_ATTACHED_FILES + 1)
        text = format_change_message(change, client)

        assert f"Файлов слишком много ({MAX_ATTACHED_FILES + 1})" in text
        assert "Текущая версия" not in text

    def test_regular_compare_reports_partial_failure(self, monitor, client):
        def raw(repo, path, ref):
            if path == "xsd/f1.xsd":
                raise GitLabError("500")
            return b"<x/>"

        client.get_raw_file.side_effect = raw
        change = self._truncated_change(monitor, client, 2)
        text = format_change_message(change, client)

        assert change.skipped == [("xsd/f1.xsd", SKIP_DOWNLOAD_FAILED)]
        assert "Приложено файлов: 1; часть файлов недоступна" in text
        assert "Текущая версия" not in text

    def test_regular_compare_all_attached_has_no_note(self, monitor, client):
        change = self._truncated_change(monitor, client, 2)
        text = format_change_message(change, client)

        assert len(change.attachments) == 2
        assert "📎" not in text  # по строкам файлов уже видно «приложена файлом»

    def test_whole_set_several_files(self, monitor, client):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331", XSD)
        client.get_last_commit.return_value = commit("bbbbbbbb")
        client.compare.side_effect = GitLabNotFoundError("404")
        client.list_files.return_value = ["xsd/a.xsd", "xsd/b.xsd"]

        change = monitor.check("331", XSD)

        assert "Текущая версия XSD-схемы приложена, файлов: 2." in (
            format_change_message(change, client)
        )

    @pytest.mark.parametrize("branch", ["rewritten", "timeout"])
    def test_list_files_failure_is_reported(self, monitor, client, store, branch):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331", XSD)
        client.get_last_commit.return_value = commit("bbbbbbbb")
        if branch == "rewritten":
            client.compare.side_effect = GitLabNotFoundError("404")
        else:
            client.compare.return_value = {
                "compare_timeout": True,
                "commits": [],
                "diffs": [],
            }
        client.list_files.side_effect = GitLabError("500")

        change = monitor.check("331", XSD)

        assert change.skipped == [("xsd/", SKIP_LIST_FAILED)]
        assert "Не удалось получить список файлов" in format_change_message(
            change, client
        )
        # Доставка текста не блокируется — baseline сдвинут
        assert store.get("331", "xsd").last_sha == "bbbbbbbb" * 5

    def test_lookup_exception_marks_both_kinds_and_continues(
        self, client, store, notify
    ):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        ok = SchematronMonitor(client, store, {"331": SEMD}.get, notify)
        ok.check_all(["331"])

        def lookup(oid):
            if oid == "331":
                raise RuntimeError("1520 broken")
            return {"OID": oid, "NAME": "x", "GIT_LINK": None}

        broken = SchematronMonitor(client, store, lookup, notify)
        broken.check_all(["331", "5"])

        for kind in ("schematron", "xsd"):
            assert store.get("331", kind).status == STATUS_ERROR
            assert store.get("331", kind).last_sha == "aaaaaaaa" * 5
            assert store.get("5", kind).status == STATUS_NO_GIT_LINK

    def test_auth_error_in_lookup_returns_accumulated(self, client, store, notify):
        client.get_last_commit.side_effect = by_kind("aaaaaaaa", "cccccccc")
        monitor = SchematronMonitor(client, store, {"331": SEMD}.get, notify)
        monitor.check_all(["331"])
        client.get_last_commit.side_effect = by_kind("bbbbbbbb", "cccccccc")
        client.compare.return_value = {"commits": [], "diffs": [SCH_DIFF]}

        def lookup(oid):
            if oid == "331":
                return SEMD
            raise GitLabAuthError("401")

        monitor.semd_lookup = lookup
        changes = monitor.check_all(["331", "9", "331"])

        assert [c.kind for c in changes] == [SCHEMATRON]
        assert notify.call_count == 1


class TestCompareAndSet:
    def test_save_if_unchanged(self, store):
        state = WatchState("1", "r@b", "a" * 40, "ok", kind="xsd")
        assert store.save_if_unchanged(None, state)
        assert not store.save_if_unchanged(None, WatchState("1", kind="xsd"))

        seen = store.get("1", "xsd")
        newer = WatchState("1", "r@b", "b" * 40, "ok", kind="xsd")
        assert store.save_if_unchanged(seen, newer)
        assert not store.save_if_unchanged(seen, WatchState("1", kind="xsd"))
        assert store.get("1", "xsd").last_sha == "b" * 40

    def test_notify_skipped_when_row_changed_during_check(
        self, monitor, client, store, notify
    ):
        client.get_last_commit.return_value = commit("aaaaaaaa")
        monitor.check("331")
        client.get_last_commit.return_value = commit("bbbbbbbb")

        def compare(repo, from_sha, to_sha):
            seen = store.get("331")
            store.save_if_unchanged(
                seen, WatchState("331", seen.git_link, "c" * 40, "ok")
            )
            return {"commits": [], "diffs": [SCH_DIFF]}

        client.compare.side_effect = compare

        assert monitor.check("331") is None
        notify.assert_not_called()
        assert store.get("331").last_sha == "c" * 40

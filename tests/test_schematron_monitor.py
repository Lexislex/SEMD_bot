from unittest.mock import MagicMock

import pytest

from plugins.schematron_monitor.formatters import (
    build_diff_text,
    diff_stats,
    format_change_message,
    is_night,
    with_inline_diff,
)
from plugins.schematron_monitor.monitor import SchematronMonitor, is_schematron_path
from services.gitlab_client import (
    GitLabAuthError,
    GitLabClient,
    GitLabError,
    GitLabNotFoundError,
)
from services.schematron_store import (
    STATUS_NO_GIT_LINK,
    STATUS_NO_SCHEMATRON,
    STATUS_NOT_IN_1520,
    STATUS_OK,
    STATUS_REPO_NOT_FOUND,
    SchematronStore,
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
        assert state.git_link == GIT_LINK
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
        assert state.git_link == "1.2.643.5.1.13.13.15.33.5"
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

    def test_check_all_continues_after_error(self, monitor, client, store):
        client.get_last_commit.side_effect = [RuntimeError("boom"), commit("aaaaaaaa")]
        monitor.check_all(["331", "331"])
        assert store.get("331").last_sha == "aaaaaaaa" * 5

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
        assert "<blockquote expandable><pre>" in text
        assert "&lt;assert test=&quot;b&quot;/&gt;" in text
        assert text.index("<pre>") < text.index("#схематрон")

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

    def test_diff_file(self, change):
        text = build_diff_text(change)
        assert "--- a/schematron/331 Schematron v1.2.sch" in text
        assert "+++ b/schematron/331 Schematron v1.3.sch" in text
        assert '+<assert test="b"/>' in text

    def test_is_night(self):
        assert is_night(23) and is_night(3)
        assert not is_night(8) and not is_night(21)

from unittest.mock import MagicMock

import pytest

from plugins.schematron_monitor.backfill import (
    BackfillError,
    apply_backfill,
    prepare_backfill,
)
from plugins.schematron_monitor.monitor import XSD, SchematronMonitor
from services.gitlab_client import GitLabClient, GitLabNotFoundError, SemdRepo
from services.schematron_store import SchematronStore, WatchState

GIT_LINK = "1.2.643.5.1.13.13.15.14.6"
REPO = SemdRepo.from_git_link(GIT_LINK)
SEMD = {"OID": "289", "NAME": "Протокол", "GIT_LINK": GIT_LINK}
SINCE = "c" * 40
HEAD = {"id": "e" * 40, "committed_date": "2026-10-12T11:23:30+00:00"}
COMMITS = [HEAD, {"id": "d" * 40, "committed_date": "2026-09-23T12:57:11+00:00"}]


@pytest.fixture
def store(tmp_path) -> SchematronStore:
    return SchematronStore(tmp_path / "fnsi.sqlite")


@pytest.fixture
def client() -> MagicMock:
    mock = MagicMock(spec=GitLabClient)
    mock.get_commit.return_value = {"id": SINCE}
    mock.get_last_commit.return_value = HEAD
    mock.merge_base.return_value = SINCE
    mock.list_commits.return_value = COMMITS
    return mock


@pytest.fixture
def monitor(client, store) -> SchematronMonitor:
    return SchematronMonitor(client, store, {"289": SEMD}.get, MagicMock())


def baseline(store, sha="e" * 40, git_link=REPO.key):
    store.save(
        WatchState(
            "289", git_link, sha, "ok", last_changed="2026-05-26T10:56:34", kind="xsd"
        )
    )


def test_plan_without_existing_baseline(monitor, client, store):
    plan = prepare_backfill(monitor, "289", XSD, "cccccccc")

    assert plan.since_sha == SINCE
    assert plan.commits == COMMITS
    assert plan.previous is None
    client.list_commits.assert_called_once_with(REPO, SINCE, HEAD["id"], path="xsd")
    assert store.get("289", "xsd") is None  # пробный прогон ничего не пишет


def test_apply_sets_baseline_keeps_last_changed(monitor, store):
    baseline(store)
    plan = prepare_backfill(monitor, "289", XSD, "cccccccc", force=True)

    apply_backfill(store, plan)

    state = store.get("289", "xsd")
    assert state.last_sha == SINCE
    assert state.git_link == REPO.key
    assert state.last_changed == "2026-05-26T10:56:34"
    assert store.get("289") is None  # схематрон не тронут


def test_existing_baseline_requires_force(monitor, store):
    baseline(store)
    with pytest.raises(BackfillError, match="--force"):
        prepare_backfill(monitor, "289", XSD, "cccccccc")


def test_repo_mismatch_refused_even_with_force(monitor, store):
    baseline(store, git_link="semd/other@1")
    with pytest.raises(BackfillError, match="не совпадает"):
        prepare_backfill(monitor, "289", XSD, "cccccccc", force=True)


def test_unknown_commit(monitor, client):
    client.get_commit.side_effect = GitLabNotFoundError("404")
    with pytest.raises(BackfillError, match="не найден"):
        prepare_backfill(monitor, "289", XSD, "deadbeef")


def test_since_not_ancestor(monitor, client):
    client.merge_base.return_value = "f" * 40
    with pytest.raises(BackfillError, match="не предшествует"):
        prepare_backfill(monitor, "289", XSD, "cccccccc")


def test_since_is_head(monitor, client):
    client.get_commit.return_value = {"id": HEAD["id"]}
    with pytest.raises(BackfillError, match="уже последний"):
        prepare_backfill(monitor, "289", XSD, "eeeeeeee")


def test_no_commits_in_range(monitor, client):
    client.list_commits.return_value = []
    with pytest.raises(BackfillError, match="объявлять нечего"):
        prepare_backfill(monitor, "289", XSD, "cccccccc")


def test_unknown_semd(monitor):
    with pytest.raises(BackfillError, match="1520"):
        prepare_backfill(monitor, "999", XSD, "cccccccc")

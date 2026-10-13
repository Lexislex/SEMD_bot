"""
Manual backfill: move a SEMD baseline back so the next cycle announces
changes that were published before monitoring of that kind started.

The baseline is only stored; the notification itself is sent by the regular
monitor cycle (one message for the whole range). The write is a
compare-and-set against the state shown to the operator, and the monitor
writes the same way, so the bot does not have to be stopped.
"""

from dataclasses import dataclass
from typing import Collection, Dict, List, Optional

from services.gitlab_client import GitLabClient, GitLabNotFoundError, SemdRepo
from services.schematron_store import STATUS_OK, SchematronStore, WatchState

from .data import WATCHED_SEMD
from .monitor import ArtifactKind, SchematronMonitor, stored_repo_key


class BackfillError(Exception):
    """Backfill is unsafe or impossible; nothing was changed."""


@dataclass
class BackfillPlan:
    semd_oid: str
    kind: ArtifactKind
    repo: SemdRepo
    since_sha: str  # full sha of the new baseline
    head: Dict  # current latest commit of the kind
    commits: List[Dict]  # commits to be announced, newest first
    previous: Optional[WatchState]


def prepare_backfill(
    monitor: SchematronMonitor,
    semd_oid: str,
    kind: ArtifactKind,
    since: str,
    force: bool = False,
    watched: Collection[str] = tuple(WATCHED_SEMD),
) -> BackfillPlan:
    """Validate a backfill without changing anything.

    Checks that the SEMD is watched by the bot, resolves to the same repository the monitor uses,
    ``since`` exists and is an ancestor of the current head, the range
    contains commits touching the kind's directory, and an existing
    baseline is overwritten only with ``force``.

    Raises:
        BackfillError: with a human-readable reason.
    """
    client: GitLabClient = monitor.client
    store: SchematronStore = monitor.store

    if semd_oid not in watched:
        raise BackfillError(
            f"СЭМД {semd_oid} не отслеживается ботом (нет в WATCHED_SEMD) — "
            "уведомления не будет"
        )

    info = monitor.semd_lookup(semd_oid)
    if info is None:
        raise BackfillError(f"СЭМД {semd_oid} не найдена в справочнике 1520")
    git_link = info.get("GIT_LINK")
    if not git_link:
        raise BackfillError(f"У СЭМД {semd_oid} не заполнен GIT_LINK")
    try:
        repo = monitor._resolve_repo(semd_oid, git_link)
    except ValueError as e:
        raise BackfillError(str(e)) from e

    previous = store.get(semd_oid, kind.key)
    if previous is not None and previous.last_sha:
        if stored_repo_key(previous.git_link) != repo.key:
            raise BackfillError(
                f"Сохранённый репозиторий {previous.git_link} не совпадает с текущим "
                f"{repo.key} — монитор всё равно сбросит baseline"
            )
        if not force:
            raise BackfillError(
                f"Baseline уже есть ({previous.last_sha[:8]}); "
                f"для перезаписи добавьте --force"
            )

    try:
        since_sha = client.get_commit(repo, since)["id"]
    except GitLabNotFoundError as e:
        raise BackfillError(f"Коммит {since} не найден в {repo.project_path}") from e

    head = client.get_last_commit(repo, path=kind.directory)
    if head is None:
        raise BackfillError(f"В ветке {repo.ref} нет файлов в {kind.directory}/")
    if since_sha == head["id"]:
        raise BackfillError(f"{since_sha[:8]} уже последний коммит {kind.directory}/")
    if client.merge_base(repo, since_sha, head["id"]) != since_sha:
        raise BackfillError(
            f"{since_sha[:8]} не предшествует {head['id'][:8]} в ветке {repo.ref}"
        )

    commits = client.list_commits(repo, since_sha, head["id"], path=kind.directory)
    if not commits:
        raise BackfillError(
            f"В диапазоне {since_sha[:8]}..{head['id'][:8]} нет коммитов в "
            f"{kind.directory}/ — объявлять нечего"
        )
    return BackfillPlan(semd_oid, kind, repo, since_sha, head, commits, previous)


def apply_backfill(store: SchematronStore, plan: BackfillPlan) -> WatchState:
    """Store the plan's baseline; the next monitor cycle announces the range.

    Raises:
        BackfillError: the stored state changed since the plan was prepared
            (e.g. the bot cycle wrote it); nothing is written.
    """
    state = WatchState(
        semd_oid=plan.semd_oid,
        git_link=plan.repo.key,
        last_sha=plan.since_sha,
        status=STATUS_OK,
        last_changed=plan.previous.last_changed if plan.previous else None,
        kind=plan.kind.key,
    )
    if not store.save_if_unchanged(plan.previous, state):
        raise BackfillError(
            "Состояние в БД изменилось после проверки (вероятно, прошёл цикл бота) — "
            "ничего не записано, запустите скрипт заново"
        )
    return state

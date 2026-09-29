"""
Schematron change detection for SEMD packages in the Minzdrav GitLab.

Algorithm per SEMD:
    1. Take the package OID (GIT_LINK) from dictionary 1520 and resolve it to
       a SemdRepo (project + branch) via the GitLab URL of dictionary 638;
       fall back to the OID heuristic if the package is missing from 638.
    2. Ask GitLab for the latest commit on the branch touching ``schematron/``.
    3. First run (or resolved repo changed): store it as baseline, no notification.
    4. New commit: compare stored sha with it, keep only ``schematron/*.sch``
       diffs and notify. The stored sha is advanced only after notify succeeds.
    5. Stored sha vanished (force-push): notify about rewritten history and
       take the new commit as baseline.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from services.gitlab_client import (
    GitLabAuthError,
    GitLabClient,
    GitLabError,
    GitLabNotFoundError,
    SemdRepo,
)
from services.schematron_store import (
    STATUS_ERROR,
    STATUS_NO_GIT_LINK,
    STATUS_NO_SCHEMATRON,
    STATUS_NOT_IN_1520,
    STATUS_OK,
    STATUS_REPO_NOT_FOUND,
    SchematronStore,
    WatchState,
)

logger = logging.getLogger(__name__)

SCHEMATRON_DIR = "schematron"


def is_schematron_path(path: Optional[str]) -> bool:
    """True for schematron files: ``schematron/**/*.sch``."""
    return (
        bool(path)
        and path.startswith(f"{SCHEMATRON_DIR}/")
        and path.lower().endswith(".sch")
    )


def is_schematron_diff(diff: Dict) -> bool:
    return is_schematron_path(diff.get("new_path")) or is_schematron_path(
        diff.get("old_path")
    )


def is_diff_truncated(diff: Dict) -> bool:
    """GitLab did not return diff content (file too large / collapsed)."""
    return bool(diff.get("too_large") or diff.get("collapsed"))


class NotificationError(Exception):
    """Notification was not delivered anywhere; baseline must not advance."""


@dataclass
class SchematronChange:
    """Detected schematron change ready to be formatted and sent."""

    semd_oid: str
    semd_name: str
    repo: SemdRepo
    from_sha: str
    to_sha: str
    head_commit: Dict
    commits: List[Dict] = field(default_factory=list)  # newest first
    diffs: List[Dict] = field(default_factory=list)
    compare_url: str = ""
    tree_url: str = ""
    history_rewritten: bool = False
    # GitLab не успел построить сравнение (compare_timeout) — diff недоступен
    compare_timed_out: bool = False
    # Полные файлы схематрона (путь, содержимое) — когда diff показать нельзя
    attachments: List[Tuple[str, bytes]] = field(default_factory=list)


SemdLookup = Callable[[str], Optional[Dict]]
# package OID (GIT_LINK of 1520) -> GitLab URL from dictionary 638
PackageLookup = Callable[[str], Optional[str]]
Notifier = Callable[[SchematronChange], None]


def stored_repo_key(stored_git_link: Optional[str]) -> Optional[str]:
    """Repo key of a stored WatchState.git_link.

    Older rows keep the raw package OID instead of ``project_path@ref``;
    they are interpreted with the heuristic that was used to check them.
    """
    if not stored_git_link or "@" in stored_git_link:
        return stored_git_link
    try:
        return SemdRepo.from_git_link(stored_git_link).key
    except ValueError:
        return stored_git_link


class SchematronMonitor:
    """Checks watched SEMD repositories and reports schematron changes."""

    def __init__(
        self,
        client: GitLabClient,
        store: SchematronStore,
        semd_lookup: SemdLookup,
        notify: Notifier,
        package_lookup: Optional[PackageLookup] = None,
    ):
        self.client = client
        self.store = store
        self.semd_lookup = semd_lookup
        self.notify = notify
        self.package_lookup = package_lookup

    def check_all(self, semd_oids: Iterable[str]) -> List[SchematronChange]:
        """Check every SEMD; one failing repository does not stop the others.

        Returns:
            Changes that were successfully notified.
        """
        changes = []
        for semd_oid in semd_oids:
            try:
                change = self.check(semd_oid)
            except GitLabAuthError as e:
                # Токен общий для всех репозиториев — продолжать бессмысленно
                logger.error(f"Проверка схематронов прервана: {e}")
                break
            except NotificationError as e:
                # Ожидаемая ситуация (Telegram недоступен / нет чатов) — без traceback
                logger.error(f"СЭМД {semd_oid}: {e}; повторим в следующем цикле")
                continue
            except Exception as e:
                logger.exception(f"Ошибка проверки схематрона СЭМД {semd_oid}: {e}")
                continue
            if change:
                changes.append(change)
        return changes

    def check(self, semd_oid: str) -> Optional[SchematronChange]:
        """Check one SEMD and notify if its schematron changed.

        Raises:
            GitLabAuthError: token problem, affects all repositories.
        """
        semd_oid = str(semd_oid)
        prev = self.store.get(semd_oid)

        info = self.semd_lookup(semd_oid)
        if info is None:
            self._save_status(semd_oid, prev, STATUS_NOT_IN_1520)
            logger.warning(f"СЭМД {semd_oid} не найдена в справочнике 1520")
            return None

        git_link = info.get("GIT_LINK")
        if not git_link:
            self._save_status(semd_oid, prev, STATUS_NO_GIT_LINK)
            logger.warning(f"У СЭМД {semd_oid} не заполнен GIT_LINK в справочнике 1520")
            return None

        try:
            repo = self._resolve_repo(semd_oid, git_link)
        except ValueError as e:
            self._save_status(semd_oid, prev, STATUS_ERROR)
            logger.warning(f"СЭМД {semd_oid}: {e}")
            return None

        # Если репозиторий/ветка сменились, старый sha относится к другой ветке —
        # начинаем заново
        same_repo = prev is not None and stored_repo_key(prev.git_link) == repo.key
        state = WatchState(
            semd_oid=semd_oid,
            git_link=repo.key,
            last_sha=prev.last_sha if same_repo else None,
            last_changed=prev.last_changed if same_repo else None,
        )

        try:
            head = self.client.get_last_commit(repo, path=SCHEMATRON_DIR)
        except GitLabAuthError:
            raise
        except GitLabNotFoundError:
            state.status = STATUS_REPO_NOT_FOUND
            self.store.save(state)
            logger.warning(
                f"СЭМД {semd_oid}: репозиторий {repo.project_path}@{repo.ref} не найден"
            )
            return None
        except GitLabError as e:
            state.status = STATUS_ERROR
            self.store.save(state)
            logger.error(f"СЭМД {semd_oid}: ошибка GitLab: {e}")
            return None

        if head is None:
            state.status = STATUS_NO_SCHEMATRON
            self.store.save(state)
            logger.info(
                f"СЭМД {semd_oid}: в ветке {repo.ref} нет файлов в {SCHEMATRON_DIR}/"
            )
            return None

        head_sha = head["id"]
        state.status = STATUS_OK

        if state.last_sha is None:
            state.last_sha = head_sha
            self.store.save(state)
            logger.info(
                f"СЭМД {semd_oid}: зафиксирована базовая версия схематрона {head_sha[:8]}"
            )
            return None

        if head_sha == state.last_sha:
            self.store.save(state)
            return None

        change = self._build_change(semd_oid, info, repo, state.last_sha, head)
        if change is None:
            # Изменения не затронули *.sch (например, .gitkeep) — тихо сдвигаем baseline
            state.last_sha = head_sha
            self.store.save(state)
            return None

        # Если уведомление не ушло — sha не сдвигаем, повторим в следующем цикле
        self.notify(change)

        state.last_sha = head_sha
        state.last_changed = head.get("committed_date")
        self.store.save(state)
        logger.info(
            f"СЭМД {semd_oid}: схематрон изменён {change.from_sha[:8]}..{head_sha[:8]}"
        )
        return change

    def _resolve_repo(self, semd_oid: str, git_link: str) -> SemdRepo:
        """Package OID -> SemdRepo: dictionary 638 first, heuristic as fallback.

        Raises:
            ValueError: the heuristic cannot parse ``git_link`` either.
        """
        url = None
        if self.package_lookup is not None:
            try:
                url = self.package_lookup(git_link)
            except Exception as e:
                logger.warning(f"СЭМД {semd_oid}: ошибка поиска пакета в 638: {e}")
        if url:
            try:
                return SemdRepo.from_url(url, git_link)
            except ValueError as e:
                logger.warning(f"СЭМД {semd_oid}: {e}, используем эвристику")
        return SemdRepo.from_git_link(git_link)

    def _build_change(
        self, semd_oid: str, info: Dict, repo: SemdRepo, from_sha: str, head: Dict
    ) -> Optional[SchematronChange]:
        to_sha = head["id"]
        change = SchematronChange(
            semd_oid=semd_oid,
            semd_name=info.get("NAME") or "",
            repo=repo,
            from_sha=from_sha,
            to_sha=to_sha,
            head_commit=head,
            compare_url=self.client.compare_url(repo, from_sha, to_sha),
            tree_url=self.client.tree_url(repo, SCHEMATRON_DIR),
        )
        try:
            comparison = self.client.compare(repo, from_sha, to_sha)
        except GitLabNotFoundError:
            logger.warning(
                f"СЭМД {semd_oid}: коммит {from_sha[:8]} не найден, история ветки переписана"
            )
            change.history_rewritten = True
            change.commits = [head]
            change.compare_url = ""
            change.attachments = self._download_files(
                repo, to_sha, self._current_schematron_files(repo, to_sha)
            )
            return change

        if comparison.get("compare_timeout"):
            # Diff-ы могли не вернуться — не молчим, прикладываем файлы целиком
            logger.warning(
                f"СЭМД {semd_oid}: таймаут сравнения {from_sha[:8]}..{to_sha[:8]} в GitLab"
            )
            change.compare_timed_out = True
            change.commits = self._schematron_commits(
                repo, from_sha, to_sha, comparison
            )
            change.attachments = self._download_files(
                repo, to_sha, self._current_schematron_files(repo, to_sha)
            )
            return change

        change.diffs = [d for d in comparison.get("diffs", []) if is_schematron_diff(d)]
        if not change.diffs:
            return None
        change.commits = self._schematron_commits(repo, from_sha, to_sha, comparison)
        truncated = [
            d["new_path"]
            for d in change.diffs
            if is_diff_truncated(d) and not d.get("deleted_file")
        ]
        change.attachments = self._download_files(repo, to_sha, truncated)
        return change

    def _current_schematron_files(self, repo: SemdRepo, ref: str) -> List[str]:
        try:
            files = self.client.list_files(repo, SCHEMATRON_DIR, ref)
        except GitLabAuthError:
            raise
        except GitLabError as e:
            logger.warning(
                f"Не удалось получить список файлов {repo.project_path}: {e}"
            )
            return []
        return [f for f in files if is_schematron_path(f)]

    def _download_files(
        self, repo: SemdRepo, ref: str, paths: List[str]
    ) -> List[Tuple[str, bytes]]:
        """Download full files; a failed download is logged and skipped."""
        result = []
        for path in paths:
            try:
                result.append((path, self.client.get_raw_file(repo, path, ref)))
            except GitLabAuthError:
                raise
            except GitLabError as e:
                logger.warning(f"Не удалось скачать {repo.project_path}/{path}: {e}")
        return result

    def _schematron_commits(
        self, repo: SemdRepo, from_sha: str, to_sha: str, comparison: Dict
    ) -> List[Dict]:
        """Commits of the range that touch schematron/, newest first.

        Falls back to all compare commits if the filtered listing fails.
        """
        try:
            commits = self.client.list_commits(
                repo, from_sha, to_sha, path=SCHEMATRON_DIR
            )
        except GitLabAuthError:
            raise
        except GitLabError as e:
            logger.warning(
                f"Не удалось получить коммиты схематрона {repo.project_path}: {e}"
            )
            commits = []
        return commits or list(reversed(comparison.get("commits", [])))

    def _save_status(
        self, semd_oid: str, prev: Optional[WatchState], status: str
    ) -> None:
        state = prev or WatchState(semd_oid=semd_oid)
        state.status = status
        self.store.save(state)

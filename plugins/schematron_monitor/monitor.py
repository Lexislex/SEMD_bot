"""
Schematron and XSD change detection for SEMD packages in the Minzdrav GitLab.

Every artifact kind (``schematron/**/*.sch``, ``xsd/**/*.xsd``) has its own
baseline and is checked independently.

Algorithm per SEMD and kind:
    1. Take the package OID (GIT_LINK) from dictionary 1520 and resolve it to
       a SemdRepo (project + branch) via the GitLab URL of dictionary 638;
       fall back to the OID heuristic if the package is missing from 638.
       This is done once per SEMD for all kinds.
    2. Ask GitLab for the latest commit on the branch touching the kind's
       directory.
    3. First run (or resolved repo changed): store it as baseline, no notification.
    4. New commit: compare stored sha with it, keep only diffs of the kind's
       files and notify. The stored sha is advanced only after notify succeeds.
    5. Stored sha vanished (force-push): notify about rewritten history and
       take the new commit as baseline.
"""

import logging
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from services.gitlab_client import (
    GitLabAuthError,
    GitLabClient,
    GitLabError,
    GitLabNotFoundError,
    SemdRepo,
)
from services.schematron_store import (
    KIND_SCHEMATRON,
    KIND_XSD,
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

logger = logging.getLogger(__name__)

# Лимит Telegram Bot API на отправку файла — 50 МБ, держим запас
MAX_DOCUMENT_BYTES = 45 * 1024 * 1024
# Больше полных файлов не скачиваем вовсе (в пакете XSD бывает ~40 файлов)
MAX_ATTACHED_FILES = 10

# Причины, по которым полный файл не приложен
SKIP_LIMIT_EXCEEDED = "limit_exceeded"
SKIP_DOWNLOAD_FAILED = "download_failed"
SKIP_TOO_LARGE = "too_large"
# Не удалось получить список файлов папки (путь — ``<directory>/``)
SKIP_LIST_FAILED = "list_failed"


@dataclass(frozen=True)
class ArtifactKind:
    """One kind of watched SEMD files with its own baseline."""

    key: str  # вид в хранилище (services.schematron_store.KIND_TABLES)
    directory: str
    extensions: Tuple[str, ...]
    label: str  # короткая подпись в меню
    genitive: str  # «текущая версия …»
    headline: str  # заголовок уведомления
    hashtag: str
    no_files_status: str  # статус, когда в папке вида нет коммитов

    def matches_path(self, path: Optional[str]) -> bool:
        """True for files of this kind: ``<directory>/**/*<ext>``."""
        return (
            bool(path)
            and path.startswith(f"{self.directory}/")
            and path.lower().endswith(self.extensions)
        )

    def matches_diff(self, diff: Dict) -> bool:
        return self.matches_path(diff.get("new_path")) or self.matches_path(
            diff.get("old_path")
        )


SCHEMATRON = ArtifactKind(
    key=KIND_SCHEMATRON,
    directory="schematron",
    extensions=(".sch",),
    label="SCH",
    genitive="схематрона",
    headline="🧩 <b>Изменён схематрон СЭМД</b>",
    hashtag="#схематрон",
    # Значение уже записано в существующих строках — сохраняем
    no_files_status=STATUS_NO_SCHEMATRON,
)
XSD = ArtifactKind(
    key=KIND_XSD,
    directory="xsd",
    extensions=(".xsd",),
    label="XSD",
    genitive="XSD-схемы",
    headline="📐 <b>Изменена XSD-схема СЭМД</b>",
    hashtag="#XSD",
    no_files_status=STATUS_NO_FILES,
)
ARTIFACT_KINDS: Tuple[ArtifactKind, ...] = (SCHEMATRON, XSD)

SCHEMATRON_DIR = SCHEMATRON.directory


def is_schematron_path(path: Optional[str]) -> bool:
    """True for schematron files: ``schematron/**/*.sch``."""
    return SCHEMATRON.matches_path(path)


def is_schematron_diff(diff: Dict) -> bool:
    return SCHEMATRON.matches_diff(diff)


def is_diff_truncated(diff: Dict) -> bool:
    """GitLab did not return diff content (file too large / collapsed)."""
    return bool(diff.get("too_large") or diff.get("collapsed"))


class NotificationError(Exception):
    """Notification was not delivered anywhere; baseline must not advance."""


@dataclass
class SchematronChange:
    """Detected schematron or XSD change ready to be formatted and sent."""

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
    # Полные файлы (путь, содержимое) — когда diff показать нельзя
    attachments: List[Tuple[str, bytes]] = field(default_factory=list)
    # Полные файлы, которые не приложены: (путь, причина SKIP_*)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    kind: ArtifactKind = SCHEMATRON


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
    """Checks watched SEMD repositories and reports schematron and XSD changes."""

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
        """Check every SEMD and kind; one failing check does not stop the others.

        Returns:
            Changes that were successfully notified (also when the cycle
            was stopped by a token error).
        """
        changes: List[SchematronChange] = []
        for semd_oid in semd_oids:
            semd_oid = str(semd_oid)
            try:
                resolved = self._resolve(semd_oid, ARTIFACT_KINDS)
            except GitLabAuthError as e:
                logger.error(f"Проверка схематронов и XSD прервана: {e}")
                return changes
            except Exception as e:
                logger.exception(f"Ошибка проверки СЭМД {semd_oid}: {e}")
                continue
            if resolved is None:
                continue
            info, repo = resolved

            for kind in ARTIFACT_KINDS:
                try:
                    change = self._check_kind(semd_oid, kind, info, repo)
                except GitLabAuthError as e:
                    # Токен общий для всех репозиториев — продолжать бессмысленно
                    logger.error(f"Проверка схематронов и XSD прервана: {e}")
                    return changes
                except NotificationError as e:
                    # Ожидаемая ситуация (Telegram недоступен / нет чатов) — без traceback
                    logger.error(
                        f"СЭМД {semd_oid} ({kind.key}): {e}; повторим в следующем цикле"
                    )
                    continue
                except Exception as e:
                    logger.exception(f"Ошибка проверки {kind.key} СЭМД {semd_oid}: {e}")
                    continue
                if change:
                    changes.append(change)
        return changes

    def check(
        self, semd_oid: str, kind: ArtifactKind = SCHEMATRON
    ) -> Optional[SchematronChange]:
        """Check one SEMD and kind and notify if its files changed.

        Raises:
            GitLabAuthError: token problem, affects all repositories.
            NotificationError: the change was not delivered.
        """
        semd_oid = str(semd_oid)
        resolved = self._resolve(semd_oid, (kind,))
        if resolved is None:
            return None
        info, repo = resolved
        return self._check_kind(semd_oid, kind, info, repo)

    def _resolve(
        self, semd_oid: str, kinds: Sequence[ArtifactKind]
    ) -> Optional[Tuple[Dict, SemdRepo]]:
        """1520 info and repository of a SEMD.

        On failure the status is stored for every kind (keeping baselines)
        and None is returned.
        """
        try:
            info = self.semd_lookup(semd_oid)
        except GitLabAuthError:
            raise
        except Exception as e:
            logger.exception(f"СЭМД {semd_oid}: ошибка поиска в справочнике 1520: {e}")
            self._save_status(semd_oid, kinds, STATUS_ERROR)
            return None
        if info is None:
            self._save_status(semd_oid, kinds, STATUS_NOT_IN_1520)
            logger.warning(f"СЭМД {semd_oid} не найдена в справочнике 1520")
            return None

        git_link = info.get("GIT_LINK")
        if not git_link:
            self._save_status(semd_oid, kinds, STATUS_NO_GIT_LINK)
            logger.warning(f"У СЭМД {semd_oid} не заполнен GIT_LINK в справочнике 1520")
            return None

        try:
            repo = self._resolve_repo(semd_oid, git_link)
        except ValueError as e:
            self._save_status(semd_oid, kinds, STATUS_ERROR)
            logger.warning(f"СЭМД {semd_oid}: {e}")
            return None
        return info, repo

    def _check_kind(
        self, semd_oid: str, kind: ArtifactKind, info: Dict, repo: SemdRepo
    ) -> Optional[SchematronChange]:
        prev = self.store.get(semd_oid, kind.key)

        # Если репозиторий/ветка сменились, старый sha относится к другой ветке —
        # начинаем заново
        same_repo = prev is not None and stored_repo_key(prev.git_link) == repo.key
        state = WatchState(
            semd_oid=semd_oid,
            git_link=repo.key,
            last_sha=prev.last_sha if same_repo else None,
            last_changed=prev.last_changed if same_repo else None,
            kind=kind.key,
        )

        try:
            head = self.client.get_last_commit(repo, path=kind.directory)
        except GitLabAuthError:
            raise
        except GitLabNotFoundError:
            state.status = STATUS_REPO_NOT_FOUND
            self._save(prev, state)
            logger.warning(
                f"СЭМД {semd_oid}: репозиторий {repo.project_path}@{repo.ref} не найден"
            )
            return None
        except GitLabError as e:
            state.status = STATUS_ERROR
            self._save(prev, state)
            logger.error(f"СЭМД {semd_oid} ({kind.key}): ошибка GitLab: {e}")
            return None

        if head is None:
            state.status = kind.no_files_status
            self._save(prev, state)
            logger.info(
                f"СЭМД {semd_oid}: в ветке {repo.ref} нет файлов в {kind.directory}/"
            )
            return None

        head_sha = head["id"]
        state.status = STATUS_OK

        if state.last_sha is None:
            state.last_sha = head_sha
            if self._save(prev, state):
                logger.info(
                    f"СЭМД {semd_oid}: зафиксирована базовая версия {kind.key} "
                    f"{head_sha[:8]}"
                )
            return None

        if head_sha == state.last_sha:
            self._save(prev, state)
            return None

        change = self._build_change(semd_oid, kind, info, repo, state.last_sha, head)
        if change is None:
            # Изменения не затронули файлы вида (например, .gitkeep) — тихо сдвигаем baseline
            state.last_sha = head_sha
            self._save(prev, state)
            return None

        if not self._unchanged(prev):
            return None

        # Если уведомление не ушло — sha не сдвигаем, повторим в следующем цикле
        self.notify(change)

        state.last_sha = head_sha
        state.last_changed = head.get("committed_date")
        if self._save(prev, state):
            logger.info(
                f"СЭМД {semd_oid}: {kind.key} изменён "
                f"{change.from_sha[:8]}..{head_sha[:8]}"
            )
        # Уведомление доставлено в любом случае — изменение в результате
        return change

    def _unchanged(self, prev: Optional[WatchState]) -> bool:
        """The stored row was not changed by another writer since ``prev``."""
        current = self.store.get(prev.semd_oid, prev.kind) if prev is not None else None
        if prev is not None and current != prev:
            logger.warning(
                f"СЭМД {prev.semd_oid} ({prev.kind}): состояние изменено извне "
                f"во время проверки, повторим в следующем цикле"
            )
            return False
        return True

    def _save(self, prev: Optional[WatchState], state: WatchState) -> bool:
        """Save unless another writer (the backfill script) changed the row.

        Returns:
            False if the write was skipped because of a concurrent change.
        """
        if self.store.save_if_unchanged(prev, state):
            return True
        logger.warning(
            f"СЭМД {state.semd_oid} ({state.kind}): состояние изменено извне "
            f"во время проверки, запись пропущена; повторим в следующем цикле"
        )
        return False

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
        self,
        semd_oid: str,
        kind: ArtifactKind,
        info: Dict,
        repo: SemdRepo,
        from_sha: str,
        head: Dict,
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
            tree_url=self.client.tree_url(repo, kind.directory),
            kind=kind,
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
            self._attach_current_files(change, to_sha)
            return change

        if comparison.get("compare_timeout"):
            # Diff-ы могли не вернуться — не молчим, прикладываем файлы целиком
            logger.warning(
                f"СЭМД {semd_oid}: таймаут сравнения {from_sha[:8]}..{to_sha[:8]} в GitLab"
            )
            change.compare_timed_out = True
            change.commits = self._kind_commits(
                repo, kind, from_sha, to_sha, comparison
            )
            self._attach_current_files(change, to_sha)
            return change

        change.diffs = [d for d in comparison.get("diffs", []) if kind.matches_diff(d)]
        if not change.diffs:
            return None
        change.commits = self._kind_commits(repo, kind, from_sha, to_sha, comparison)
        # Переименование из папки вида наружу — новый путь уже не наш файл
        truncated = [
            d["new_path"]
            for d in change.diffs
            if is_diff_truncated(d)
            and not d.get("deleted_file")
            and kind.matches_path(d.get("new_path"))
        ]
        self._attach_files(change, to_sha, truncated)
        return change

    def _attach_current_files(self, change: SchematronChange, ref: str) -> None:
        """Attach all current files of the change's kind at ``ref``."""
        kind, repo = change.kind, change.repo
        try:
            files = self.client.list_files(repo, kind.directory, ref)
        except GitLabAuthError:
            raise
        except GitLabError as e:
            logger.warning(
                f"Не удалось получить список файлов {repo.project_path}: {e}"
            )
            change.skipped.append((f"{kind.directory}/", SKIP_LIST_FAILED))
            return
        self._attach_files(change, ref, [f for f in files if kind.matches_path(f)])

    def _attach_files(
        self, change: SchematronChange, ref: str, paths: List[str]
    ) -> None:
        """Download full files into ``change.attachments``.

        Nothing is downloaded when there are more than MAX_ATTACHED_FILES
        files; every file that is not attached is recorded in
        ``change.skipped`` with its reason.
        """
        repo = change.repo
        if len(paths) > MAX_ATTACHED_FILES:
            logger.warning(
                f"СЭМД {change.semd_oid}: {len(paths)} файлов {change.kind.key} — "
                f"больше {MAX_ATTACHED_FILES}, не прикладываем"
            )
            change.skipped += [(path, SKIP_LIMIT_EXCEEDED) for path in paths]
            return
        for path in paths:
            try:
                content = self.client.get_raw_file(repo, path, ref)
            except GitLabAuthError:
                raise
            except GitLabError as e:
                logger.warning(f"Не удалось скачать {repo.project_path}/{path}: {e}")
                change.skipped.append((path, SKIP_DOWNLOAD_FAILED))
                continue
            if len(content) > MAX_DOCUMENT_BYTES:
                logger.warning(
                    f"Файл {path} ({len(content)} байт) превышает лимит Telegram, "
                    f"не прикладываем"
                )
                change.skipped.append((path, SKIP_TOO_LARGE))
                continue
            change.attachments.append((path, content))

    def _kind_commits(
        self,
        repo: SemdRepo,
        kind: ArtifactKind,
        from_sha: str,
        to_sha: str,
        comparison: Dict,
    ) -> List[Dict]:
        """Commits of the range that touch the kind's directory, newest first.

        Falls back to all compare commits if the filtered listing fails.
        """
        try:
            commits = self.client.list_commits(
                repo, from_sha, to_sha, path=kind.directory
            )
        except GitLabAuthError:
            raise
        except GitLabError as e:
            logger.warning(
                f"Не удалось получить коммиты {kind.key} {repo.project_path}: {e}"
            )
            commits = []
        return commits or list(reversed(comparison.get("commits", [])))

    def _save_status(
        self, semd_oid: str, kinds: Sequence[ArtifactKind], status: str
    ) -> None:
        """Store a status for every kind, keeping the existing baselines."""
        for kind in kinds:
            prev = self.store.get(semd_oid, kind.key)
            state = (
                replace(prev, status=status)
                if prev is not None
                else WatchState(semd_oid=semd_oid, status=status, kind=kind.key)
            )
            self._save(prev, state)

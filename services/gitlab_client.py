"""
Client for the Minzdrav GitLab (git.minzdrav.gov.ru) that hosts SEMD packages.

Repository resolution:
    * the 1520 dictionary column GIT_LINK holds a package OID such as
      ``1.2.643.5.1.13.13.15.33.4``;
    * the source of truth is dictionary 638 (registry of SEMD implementation
      guides): its column GIT_LINK maps the package OID to a URL like
      ``<base>/semd/1.2.643.5.1.13.13.15.33/-/tree/1.2.643.5.1.13.13.15.33.4``;
    * the package OID usually matches the heuristic "project ``semd/<OID
      without last segment>``, branch = OID", but not always: packages
      ``...15.36.5`` (SEMD 113) and ``...15.38.2`` (SEMD 114) live in
      ``semd/...15.35`` and ``semd/...15.37``. The heuristic is only a
      fallback for packages missing from 638;
    * schematron files are stored in the ``schematron/`` directory.
"""

import logging
from dataclasses import dataclass
from time import sleep
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote, unquote, urlsplit

import requests

from services.proxy_utils import build_proxies, build_url
from utils.retry import backoff_delay

logger = logging.getLogger(__name__)

SEMD_GROUP = "semd"
# Разделители project_path и ref в URL GitLab (в 638 встречаются оба)
REF_URL_MARKERS = ("/-/tree/", "/-/blob/")
MAX_RETRY_AFTER = 60  # не ждём по Retry-After дольше, сек


class GitLabError(Exception):
    """Generic GitLab API error."""


class GitLabNotFoundError(GitLabError):
    """Project, ref or commit is missing (or hidden from the token)."""


class GitLabAuthError(GitLabError):
    """Token is missing, invalid or lacks the read_api scope."""


@dataclass(frozen=True)
class SemdRepo:
    """GitLab location of one SEMD revision."""

    git_link: str  # package OID from 1520 (shown in notifications)
    project_path: str
    ref: str

    @property
    def key(self) -> str:
        """Resolved location ``project_path@ref`` (used to detect remapping)."""
        return f"{self.project_path}@{self.ref}"

    @classmethod
    def from_url(cls, url: str, git_link: str) -> "SemdRepo":
        """Build repo location from a GitLab URL of the 638 dictionary.

        Args:
            url: ``<base>/<project_path>/-/tree/<ref>`` (or ``/-/blob/``).
            git_link: package OID from 1520 this URL belongs to.

        Raises:
            ValueError: if the URL does not contain a project path and a ref.
        """
        path = unquote(urlsplit((url or "").strip()).path)
        for marker in REF_URL_MARKERS:
            project_path, sep, ref = path.partition(marker)
            project_path, ref = project_path.strip("/"), ref.strip("/")
            if sep and project_path and ref:
                return cls(
                    git_link=(git_link or "").strip(),
                    project_path=project_path,
                    ref=ref,
                )
        raise ValueError(f"Некорректная ссылка на репозиторий СЭМД: {url!r}")

    @classmethod
    def from_git_link(cls, git_link: str, group: str = SEMD_GROUP) -> "SemdRepo":
        """Guess repo location from a GIT_LINK value of the 1520 dictionary.

        Fallback for packages missing from dictionary 638 (see module docstring).

        Args:
            git_link: package id like ``1.2.643.5.1.13.13.15.33.4``.
            group: GitLab group that holds SEMD projects.

        Raises:
            ValueError: if the value does not look like ``<kind>.<revision>``.
        """
        git_link = (git_link or "").strip()
        kind, sep, revision = git_link.rpartition(".")
        if not sep or not kind or not revision.isdigit():
            raise ValueError(f"Некорректное значение GIT_LINK: {git_link!r}")
        return cls(git_link=git_link, project_path=f"{group}/{kind}", ref=git_link)


class GitLabClient:
    """Thin read-only wrapper over the GitLab REST API v4 with retries."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 30,
        max_retries: int = 3,
        verify: Union[bool, str] = True,
        proxies: Optional[Dict[str, str]] = None,
    ):
        if not token:
            raise GitLabAuthError("Отсутствует GITLAB_TOKEN в конфигурации")
        self.base_url = base_url.rstrip("/")
        self.api_url = build_url(self.base_url, "api/v4")
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.session = requests.Session()
        self.session.headers.update({"PRIVATE-TOKEN": token})
        self.session.verify = verify
        if proxies:
            self.session.proxies.update(proxies)

    @classmethod
    def from_config(cls, cfg) -> "GitLabClient":
        """Create client from the application Config."""
        # Сертификат Минздрава подходит и для git.minzdrav.gov.ru
        cert = cfg.paths.mzrf_cert_path
        verify: Union[bool, str] = str(cert) if cert and cert.exists() else True
        proxies = (
            build_proxies(cfg.gitlab.url, force=True) if cfg.gitlab.use_proxy else None
        )
        return cls(
            base_url=cfg.gitlab.url,
            token=cfg.gitlab.token,
            timeout=cfg.gitlab.request_timeout,
            max_retries=cfg.gitlab.max_retries,
            verify=verify,
            proxies=proxies,
        )

    # ------------------------------------------------------------------ HTTP

    def _request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """GET an API endpoint with retries on timeouts, connection errors and 5xx.

        Returns:
            Successful (2xx) response.
        """
        url = build_url(self.api_url, endpoint)
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.SSLError as e:
                raise GitLabError(
                    f"SSL ошибка при запросе к GitLab {endpoint}: {e}"
                ) from e
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as e:
                last_error = e
                logger.warning(
                    f"Ошибка соединения с GitLab {endpoint} "
                    f"(попытка {attempt}/{self.max_retries}): {e}"
                )
            except requests.exceptions.RequestException as e:
                raise GitLabError(f"Ошибка запроса к GitLab {endpoint}: {e}") from e
            else:
                status = response.status_code
                if status in (401, 403):
                    raise GitLabAuthError(
                        f"GitLab вернул {status} для {endpoint}: "
                        f"проверьте GITLAB_TOKEN (нужен scope read_api)"
                    )
                if status == 404:
                    raise GitLabNotFoundError(f"GitLab: не найдено {endpoint}")
                if status == 429 or 500 <= status < 600:
                    # 429 — GitLab ограничивает частоту запросов, это временно
                    last_error = GitLabError(f"HTTP {status}")
                    logger.warning(
                        f"HTTP {status} от GitLab {endpoint} "
                        f"(попытка {attempt}/{self.max_retries})"
                    )
                    if attempt < self.max_retries:
                        sleep(self._retry_delay(response, attempt))
                    continue
                if status >= 400:
                    raise GitLabError(
                        f"GitLab вернул {status} для {endpoint}: {response.text[:200]}"
                    )
                return response

            if attempt < self.max_retries:
                sleep(backoff_delay(attempt))

        raise GitLabError(
            f"Не удалось получить ответ от GitLab {endpoint} "
            f"после {self.max_retries} попыток: {last_error}"
        )

    @staticmethod
    def _retry_delay(response: requests.Response, attempt: int) -> float:
        """Honor Retry-After (seconds) if present, else exponential backoff."""
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(int(retry_after), MAX_RETRY_AFTER)
        return backoff_delay(attempt)

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET an API endpoint and decode JSON."""
        response = self._request(endpoint, params)
        try:
            return response.json()
        except ValueError as e:
            raise GitLabError(f"Невалидный JSON от GitLab {endpoint}: {e}") from e

    @staticmethod
    def _project_id(repo: SemdRepo) -> str:
        return quote(repo.project_path, safe="")

    # ------------------------------------------------------------------- API

    def get_last_commit(
        self, repo: SemdRepo, path: Optional[str] = None
    ) -> Optional[Dict]:
        """Return the latest commit on the repo ref, optionally touching ``path``.

        Returns:
            Commit dict (``id``, ``short_id``, ``title``, ``author_name``,
            ``committed_date``, ...) or None if no commit touches ``path``.

        Raises:
            GitLabNotFoundError: project or ref does not exist.
        """
        params: Dict[str, Any] = {"ref_name": repo.ref, "per_page": 1}
        if path:
            params["path"] = path
        commits = self._get(
            f"projects/{self._project_id(repo)}/repository/commits", params
        )
        if not commits:
            # GitLab отдаёт [] и для несуществующей ветки — проверяем её явно,
            # чтобы получить GitLabNotFoundError
            self._get(
                f"projects/{self._project_id(repo)}/repository/branches/"
                f"{quote(repo.ref, safe='')}"
            )
            return None
        return commits[0]

    def list_commits(
        self,
        repo: SemdRepo,
        from_sha: str,
        to_sha: str,
        path: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Commits in ``from_sha..to_sha`` (newest first), optionally touching ``path``."""
        params: Dict[str, Any] = {
            "ref_name": f"{from_sha}..{to_sha}",
            "per_page": limit,
        }
        if path:
            params["path"] = path
        return self._get(
            f"projects/{self._project_id(repo)}/repository/commits", params
        )

    def list_files(self, repo: SemdRepo, path: str, ref: str) -> List[str]:
        """Paths of all files under ``path`` at ``ref`` (branch or sha)."""
        files: List[str] = []
        page = 1
        while True:
            items = self._get(
                f"projects/{self._project_id(repo)}/repository/tree",
                {
                    "ref": ref,
                    "path": path,
                    "recursive": "true",
                    "per_page": 100,
                    "page": page,
                },
            )
            files += [item["path"] for item in items if item.get("type") == "blob"]
            if len(items) < 100:
                return files
            page += 1

    def get_raw_file(self, repo: SemdRepo, file_path: str, ref: str) -> bytes:
        """Raw content of ``file_path`` at ``ref`` (branch or sha)."""
        response = self._request(
            f"projects/{self._project_id(repo)}/repository/files/"
            f"{quote(file_path, safe='')}/raw",
            {"ref": ref},
        )
        return response.content

    def compare(self, repo: SemdRepo, from_sha: str, to_sha: str) -> Dict:
        """Compare two commits.

        Returns:
            Dict with ``commits`` (oldest first) and ``diffs`` (list of dicts with
            ``old_path``, ``new_path``, ``diff``, ``new_file``, ``renamed_file``,
            ``deleted_file``, ``too_large``, ``collapsed``).

        Raises:
            GitLabNotFoundError: one of the commits no longer exists
                (e.g. history was rewritten with force-push).
        """
        data = self._get(
            f"projects/{self._project_id(repo)}/repository/compare",
            {"from": from_sha, "to": to_sha},
        )
        if not isinstance(data, dict):
            raise GitLabError(f"Неожиданный ответ GitLab compare: {type(data)}")
        return data

    # ------------------------------------------------------------------ URLs

    def project_url(self, repo: SemdRepo) -> str:
        return f"{self.base_url}/{repo.project_path}"

    def tree_url(self, repo: SemdRepo, path: str = "") -> str:
        suffix = f"/{quote(path)}" if path else ""
        return f"{self.project_url(repo)}/-/tree/{quote(repo.ref)}{suffix}"

    def compare_url(self, repo: SemdRepo, from_sha: str, to_sha: str) -> str:
        return f"{self.project_url(repo)}/-/compare/{from_sha}...{to_sha}"

    def commit_url(self, repo: SemdRepo, sha: str) -> str:
        return f"{self.project_url(repo)}/-/commit/{sha}"

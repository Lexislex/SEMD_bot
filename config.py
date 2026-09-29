# config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

# Корень проекта (по файлу config.py)
PROJECT_ROOT = Path(__file__).resolve().parent

# Общие, проектные пути/файлы — не секреты
DATA_DIR = PROJECT_ROOT / "env" / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
FILES_DIR = PROJECT_ROOT / "files"
CERT_DIR = PROJECT_ROOT / "env" / "crts"

USER_DB_PATH = DATA_DIR / "user_data.sqlite"
FNSI_DB_PATH = DATA_DIR / "fnsi_data.sqlite"

MZRF_CERT_PATH = CERT_DIR / "rosminzdrav.crt"

# Значения по умолчанию для несекретных параметров проекта
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_ENV = "production"  # "development" | "staging" | "production"
DEFAULT_GITLAB_URL = "https://git.minzdrav.gov.ru"


@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    env: str
    log_level: str
    service_unit_path: Path  # например, для systemd unit-файла (если используется)
    telegram_api_base_url: Optional[
        str
    ]  # кастомный reverse-proxy endpoint для Telegram API


@dataclass(frozen=True)
class AccountsConfig:
    admin_ids: List[int]
    updates_mailing_list: List[int]


@dataclass(frozen=True)
class PathsConfig:
    project_root: Path
    data_dir: Path
    logs_dir: Path
    files_dir: Path
    user_db_path: Path
    fnsi_db_path: Path
    mzrf_cert_path: Path


@dataclass(frozen=True)
class ExternalAPIsConfig:
    # Секреты и токены — только из .env
    fnsi_api_url: Optional[str]
    fnsi_api_key: Optional[str]
    fnsi_files_url: Optional[str]
    # Таймаут одного запроса к ФНСИ (сек)
    fnsi_request_timeout: int
    # Количество повторных попыток при таймаутах/5xx ФНСИ
    fnsi_max_retries: int
    # добавляйте другие интеграции по мере роста


@dataclass(frozen=True)
class GitLabConfig:
    # GitLab Минздрава с пакетами СЭМД (схематроны, XSD, руководства)
    url: str
    token: Optional[str]
    # Таймаут одного запроса к GitLab (сек)
    request_timeout: int
    # Количество попыток при таймаутах/5xx GitLab
    max_retries: int
    # Использовать PROXY_* для запросов к GitLab
    use_proxy: bool


@dataclass(frozen=True)
class ProxyConfig:
    enabled: bool
    proxy_type: Optional[str]  # http, https, socks5
    host: Optional[str]
    port: Optional[int]
    user: Optional[str]
    password: Optional[str]


@dataclass(frozen=True)
class Config:
    app: AppConfig
    accounts: AccountsConfig
    paths: PathsConfig
    apis: ExternalAPIsConfig
    proxy: ProxyConfig
    gitlab: GitLabConfig


# Кеш конфигурации, чтобы не читать .env многократно
_CONFIG: Optional[Config] = None


def _read_env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    # Убираем окружающие пробелы и кавычки, которые часто оставляют в .env
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        val = val[1:-1]
    return val if val != "" else default


def _read_int_env(name: str, default: int, minimum: int) -> int:
    """Read an integer env variable, falling back to default on invalid input."""
    try:
        return max(minimum, int(_read_env(name, str(default))))
    except ValueError:
        return default


def _read_int_list_env(name: str, required: bool = False) -> List[int]:
    """Read a comma-separated list of integers (Telegram IDs, ports).

    Raises:
        ValueError: the variable is required but empty, or contains a non-integer.
    """
    raw = _read_env(name, "")
    try:
        values = [int(item.strip()) for item in raw.split(",") if item.strip()]
    except ValueError as e:
        raise ValueError(
            f"{name} должен содержать целые числа через запятую: {raw!r}"
        ) from e
    if required and not values:
        raise ValueError(f"Не задана обязательная переменная окружения {name} (.env)")
    return values


def get_config() -> Config:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    # Читаем секреты/переменные среды из .env
    bot_token = _read_env("BOT_TOKEN")
    env = _read_env("ENV", DEFAULT_ENV)
    log_level = _read_env("LOG_LEVEL", DEFAULT_LOG_LEVEL)

    # Внешние API
    fnsi_api_url = _read_env("FNSI_API_URL")
    fnsi_files_url = _read_env("FNSI_FILES_URL")
    fnsi_api_key = _read_env("FNSI_API_KEY")

    fnsi_request_timeout = _read_int_env("FNSI_REQUEST_TIMEOUT", 60, minimum=5)
    fnsi_max_retries = _read_int_env("FNSI_MAX_RETRIES", 3, minimum=1)

    # GitLab Минздрава
    gitlab_url = _read_env("GITLAB_URL", DEFAULT_GITLAB_URL)
    gitlab_token = _read_env("GITLAB_TOKEN")
    gitlab_request_timeout = _read_int_env("GITLAB_REQUEST_TIMEOUT", 30, minimum=5)
    gitlab_max_retries = _read_int_env("GITLAB_MAX_RETRIES", 3, minimum=1)
    gitlab_use_proxy = _read_env("GITLAB_USE_PROXY", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    # Настройки прокси
    proxy_enabled = _read_env("PROXY_ENABLED", "false").lower() in ("true", "1", "yes")
    proxy_type = _read_env("PROXY_TYPE", "http")
    proxy_host = _read_env("PROXY_HOST")
    proxy_port = _read_int_list_env("PROXY_PORT")
    proxy_port = proxy_port[0] if proxy_port else None
    proxy_user = _read_env("PROXY_USER")
    proxy_pass = _read_env("PROXY_PASS")

    telegram_api_base_url = _read_env("TELEGRAM_API_BASE_URL")

    app_cfg = AppConfig(
        bot_token=bot_token,
        env=env,
        log_level=log_level,
        service_unit_path=PROJECT_ROOT / "env" / "SEMD_bot.service",
        telegram_api_base_url=telegram_api_base_url,
    )

    accounts_cfg = AccountsConfig(
        admin_ids=_read_int_list_env("ADMIN_ID", required=True),
        updates_mailing_list=_read_int_list_env("UPDS_MAILING_LIST"),
    )

    paths_cfg = PathsConfig(
        project_root=PROJECT_ROOT,
        data_dir=DATA_DIR,
        logs_dir=LOGS_DIR,
        files_dir=FILES_DIR,
        user_db_path=USER_DB_PATH,
        fnsi_db_path=FNSI_DB_PATH,
        mzrf_cert_path=MZRF_CERT_PATH,
    )

    apis_cfg = ExternalAPIsConfig(
        fnsi_api_url=fnsi_api_url,
        fnsi_files_url=fnsi_files_url,
        fnsi_api_key=fnsi_api_key,
        fnsi_request_timeout=fnsi_request_timeout,
        fnsi_max_retries=fnsi_max_retries,
    )

    proxy_cfg = ProxyConfig(
        enabled=proxy_enabled,
        proxy_type=proxy_type,
        host=proxy_host,
        port=proxy_port,
        user=proxy_user,
        password=proxy_pass,
    )

    gitlab_cfg = GitLabConfig(
        url=gitlab_url,
        token=gitlab_token,
        request_timeout=gitlab_request_timeout,
        max_retries=gitlab_max_retries,
        use_proxy=gitlab_use_proxy,
    )

    _CONFIG = Config(
        app=app_cfg,
        accounts=accounts_cfg,
        paths=paths_cfg,
        apis=apis_cfg,
        proxy=proxy_cfg,
        gitlab=gitlab_cfg,
    )
    return _CONFIG

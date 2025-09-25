# config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

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


@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    env: str
    log_level: str
    service_unit_path: Path  # например, для systemd unit-файла (если используется)

@dataclass(frozen=True)
class AccountsConfig:
    admin_id: int
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
    # добавляйте другие интеграции по мере роста

@dataclass(frozen=True)
class Config:
    app: AppConfig
    accounts: AccountsConfig
    paths: PathsConfig
    apis: ExternalAPIsConfig

# Кеш конфигурации, чтобы не читать .env многократно
_CONFIG: Optional[Config] = None


def _read_env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name)
    return val if val is not None and val != "" else default


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

    app_cfg = AppConfig(
        bot_token=bot_token,
        env=env,
        log_level=log_level,
        service_unit_path=PROJECT_ROOT / "env" / "SEMD_bot.service",
    )

    accounts_cfg = AccountsConfig(
        admin_id = int(_read_env("ADMIN_ID")),
        updates_mailing_list = _read_env("UPDS_MAILING_LIST").split(","),
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
    )

    _CONFIG = Config(
        app=app_cfg,
        accounts=accounts_cfg,
        paths=paths_cfg,
        apis=apis_cfg,
    )
    return _CONFIG
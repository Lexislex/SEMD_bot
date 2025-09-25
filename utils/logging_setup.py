import logging
import logging.config
from pathlib import Path

def setup_logging(cfg) -> None:
    logs_dir: Path = cfg.paths.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, (cfg.app.log_level or "INFO").upper(), logging.INFO)

    LOG_FILE = logs_dir / "semd_bot.log"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "file": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "console",
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "level": log_level,
                "formatter": "file",
                "filename": str(LOG_FILE),
                "when": "midnight",
                "backupCount": 7,
                "encoding": "utf-8",
                "utc": False,
            },
        },
        "loggers": {
            # Тихие сторонние библиотеки
            "urllib3": {"level": "WARNING", "handlers": ["console", "file"], "propagate": False},
            "requests": {"level": "WARNING", "handlers": ["console", "file"], "propagate": False},
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "file"],
        },
    }

    logging.config.dictConfig(config)
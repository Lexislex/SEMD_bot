# SEMD Bot

Telegram bot for monitoring medical references (SEMD, NSI) from Russian Ministry of Health.

## Tech Stack

- Python ≥3.10, Poetry
- pyTelegramBotAPI, SQLite, schedule, pandas

## Project Structure

```
core/           - bot core (bot.py, plugin_manager.py, scheduler.py)
plugins/        - plugin system (BasePlugin, ScheduledPlugin)
services/       - fnsi_client, database_service, proxy_utils
utils/          - logging, database, formatters, file utils
env/data/       - SQLite databases (user_data, fnsi_data)
scripts/        - helper scripts (database management, testing)
docs/           - documentation (dev-only branch)
tests/          - tests (dev-only branch)
```

## Commands

```bash
poetry install                  # install dependencies
poetry run python main.py       # run bot
poetry run pytest               # run tests
```

## Configuration

Environment variables in `.env` (see `env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| BOT_TOKEN | Yes | Telegram bot token |
| ADMIN_ID | Yes | Admin Telegram IDs (comma-separated) |
| UPDS_MAILING_LIST | Yes | Chat IDs for notifications |
| FNSI_API_KEY | Yes | FNSI API key |
| ENV | No | development/production (default: production) |
| LOG_LEVEL | No | DEBUG/INFO/WARNING/ERROR (default: INFO) |
| PROXY_* | No | Proxy settings if needed |

## Architecture

### Plugin System

- **BasePlugin** - reactive plugins (commands, callbacks)
- **ScheduledPlugin** - scheduled tasks (inherits BasePlugin)

### Threading

- Main thread: TeleBot polling
- Daemon thread: TaskScheduler (for ScheduledPlugins)

### Key Files

- `main.py` - entry point, loads plugins
- `config.py` - configuration (dataclasses from .env)
- `plugins/base.py` - base plugin classes

## Rules

1. **Documentation** → `docs/` folder only
2. **New plugins** → `plugins/` following existing patterns
3. **Logging** → use `logging` module, not `print()`
4. **Tests** → `tests/` folder

## Git Workflow

| Branch | Purpose | Dev files allowed |
|--------|---------|-------------------|
| master | stable, production | No (tests/, docs/, .claude/) |
| develop | development | Yes |

- Direct push to master is blocked
- Merge to master only via PR
- GitHub Actions checks for forbidden files

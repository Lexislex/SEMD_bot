# Schematron Monitor Plugin

## Description

Watches the Minzdrav GitLab (`git.minzdrav.gov.ru`) for schematron changes of
selected SEMD and posts a summary plus the diff to `UPDS_MAILING_LIST`.

## How it works

1. **SEMD list**: `data.py` → `WATCHED_SEMD`, which holds OIDs from dictionary 1520 (column `OID`).
2. **Repository lookup**: the `GIT_LINK` column of dictionary 1520 holds a package id
   such as `1.2.643.5.1.13.13.15.33.4`:
   - project: `semd/1.2.643.5.1.13.13.15.33` (the id without its last segment);
   - branch: `1.2.643.5.1.13.13.15.33.4` (the full id, one branch per revision);
   - schematron files: `schematron/*.sch`.
3. **Change detection**: every cycle the plugin asks GitLab for the latest commit on the
   branch that touches `schematron/`. It makes one request per SEMD and compares
   the result with the SHA stored in `fnsi_data.sqlite` → `schematron_watch`.
4. **Diff**: if the SHA changed, `repository/compare` returns the diff. Only
   `schematron/**/*.sch` files are kept. Commits come from
   `commits?ref_name=<old>..<new>&path=schematron`.
5. **Notification**: an HTML summary (files with `+N / −M`, commits, a link to the GitLab compare page).
   A short diff is included inline, and the full diff is attached as a `.diff` file.
   Messages are silent from 22:00 to 08:00.

### Edge cases

| Situation | Behaviour |
|---|---|
| First check / `GIT_LINK` changed | Store the baseline SHA, no notification |
| Only non-schematron files changed | Advance the SHA silently |
| Stored SHA vanished (force-push) | Notify "history rewritten", take the new baseline |
| Project/branch not found (or hidden from the token) | Status `repo_not_found`, retried every cycle |
| Telegram delivery failed for every chat | SHA is not advanced, retried next cycle |
| Invalid token (401/403) | The cycle stops, error logged |

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `GITLAB_URL` | `https://git.minzdrav.gov.ru` | GitLab base URL |
| `GITLAB_TOKEN` | — | Personal access token with the `read_api` scope (**required**, the plugin is disabled without it) |
| `GITLAB_REQUEST_TIMEOUT` | `30` | Request timeout, seconds |
| `GITLAB_MAX_RETRIES` | `3` | Attempts on timeouts / 5xx |
| `GITLAB_USE_PROXY` | `false` | Route GitLab requests through `PROXY_*` |

TLS is verified with `env/crts/rosminzdrav.crt`, the same certificate used for FNSI.

## Buttons

- 🧩 Схематроны СЭМД: lists the watched SEMD with the status and date of the last change
- « Назад в меню: returns to the main menu

## Schedule

- Development: every minute
- Production: every 60 minutes

## Access

Available to all users (`access_level = "all"`).

## Files

- `plugin.py`: plugin class (ScheduledPlugin)
- `monitor.py`: change detection (no Telegram dependencies)
- `formatters.py`: message and `.diff` formatting
- `handlers.py`: sending notifications, menu
- `data.py`: watched SEMD list
- `services/gitlab_client.py`: GitLab REST client with retries
- `services/schematron_store.py`: SQLite state (`schematron_watch`)

## Version

1.0.0

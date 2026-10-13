# Schematron Monitor Plugin

## Description

Watches the Minzdrav GitLab (`git.minzdrav.gov.ru`) for schematron and XSD
schema changes of selected SEMD and posts a summary plus the diff to
`UPDS_MAILING_LIST`.

Two artifact kinds are tracked independently, each with its own baseline and
its own notification:

| Kind | Files | Table | Header / hashtag |
|---|---|---|---|
| Schematron | `schematron/**/*.sch` | `schematron_watch` | 🧩 Изменён схематрон / `#схематрон` |
| XSD | `xsd/**/*.xsd` (incl. `XSD CDA/coreschemas`) | `xsd_watch` | 📐 Изменена XSD-схема / `#XSD` |

The tables are separate so that rolling the code back needs no database
changes (the old code reads `schematron_watch` only). A newly added kind starts
with a silent baseline: changes published before it was deployed are not
announced.

## How it works

1. **SEMD list**: `data.py` → `WATCHED_SEMD`, which holds OIDs from dictionary 1520 (column `OID`).
2. **Repository lookup**: the `GIT_LINK` column of dictionary 1520 holds a package OID
   such as `1.2.643.5.1.13.13.15.33.4`. The package is looked up in dictionary 638
   (registry of SEMD implementation guides), whose `GIT_LINK` column holds the GitLab URL
   `<base>/<project>/-/tree/<branch>` (sometimes `/-/blob/`):
   - SEMD 113: package `…15.36.5` → project `semd/…15.35`, branch `…15.35.5`;
   - if the package is missing from 638 (or 638 is not loaded yet), the project is guessed
     as `semd/<OID without its last segment>` and the branch as the full OID;
   - schematron files: `schematron/*.sch`; XSD schemas: `xsd/**/*.xsd`.

   Dictionary 638 is monitored by the NSI Update Checker (`notify: False`), so new versions
   land in `nsi_passport` and are reloaded automatically.
3. **Change detection**: every cycle the plugin resolves the repository once per SEMD
   and asks GitLab for the latest commit on the branch that touches the kind's
   directory (`schematron/`, `xsd/`). The result is compared with the SHA stored in
   `fnsi_data.sqlite` → `schematron_watch` / `xsd_watch`.
4. **Diff**: if the SHA changed, `repository/compare` returns the diff. Only files of
   the kind are kept. Commits come from
   `commits?ref_name=<old>..<new>&path=<directory>`.
5. **Notification**: an HTML summary (files with `+N / −M`, commits, a link to the GitLab compare page).
   A short diff is included inline, and the full diff is attached as a `.diff` file.
   Messages are silent from 22:00 to 08:00.

### Edge cases

| Situation | Behaviour |
|---|---|
| First check / resolved repository changed (`project@branch` in `git_link`) | Store the baseline SHA, no notification |
| Only files of another kind changed | Advance the SHA silently |
| Stored SHA vanished (force-push) | Notify "history rewritten", attach the kind's current files in full, take the new baseline |
| GitLab truncated the diff (`too_large` / `collapsed`) | Attach the new version of that file in full |
| GitLab compare timed out (`compare_timeout`) | Notify "diff unavailable", attach the kind's current files in full |
| More than 10 full files to attach | Nothing is downloaded; the message says the files are in GitLab |
| Full file failed to download or exceeds 45 MB | Not attached; the message says which part is attached |
| File list unavailable (force-push / compare timeout) | Nothing attached; the message says so, delivery is not blocked |
| 1520 lookup raised | Status `error` for both kinds, baselines kept, next SEMD is checked |
| Both kinds changed in one cycle | Two separate notifications |
| One kind failed (delivery or GitLab error) | The other kind of the same SEMD is still checked and delivered |
| Too many changed files for one message | The file list is shortened ("…и ещё N"); the full list is in the `.diff` |
| Project/branch not found (or hidden from the token) | Status `repo_not_found`, retried every cycle |
| Message not delivered to any chat, or `UPDS_MAILING_LIST` is empty | SHA is not advanced, retried next cycle |
| Attachment failed to send | Logged; the message still counts as delivered (it has GitLab links) |
| GitLab 429 / 5xx / timeout | Retried with backoff (honors `Retry-After`, up to 60 s) |
| Invalid token (401/403) | The cycle stops, error logged; changes already delivered are kept |

## Backfill

A new kind starts with a silent baseline, so changes published before it was
deployed are not announced. To announce them, move the baseline back with
`scripts/schematron_backfill.py`; the next regular cycle sends one message for
the whole range:

```bash
# dry run: checks and the commits that will be announced, nothing is written
uv run python scripts/schematron_backfill.py --semd 289 --kind xsd --since c682b1e3
# write; --force is needed when a baseline already exists
uv run python scripts/schematron_backfill.py --semd 289 --kind xsd --since c682b1e3 --force --apply
```

The script refuses when the stored repository differs from the resolved one,
`--since` is not an ancestor of the current head, or the range has no commits
in the kind's directory.

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

- 🧩 Схематроны и XSD СЭМД: lists the watched SEMD with the status of each kind and the
  date of its last delivered change (`SCH ✅ (изм. 26.05.2026) · XSD ✅`)
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
- `backfill.py`: baseline backfill logic (CLI: `scripts/schematron_backfill.py`)
- `services/gitlab_client.py`: GitLab REST client with retries
- `services/schematron_store.py`: SQLite state (`schematron_watch`, `xsd_watch`)

## Version

1.1.0

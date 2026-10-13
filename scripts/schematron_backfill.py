#!/usr/bin/env python3
"""
Догон изменений схематрона/XSD, вышедших до начала мониторинга.

Сдвигает baseline СЭМД назад на указанный коммит. Сам скрипт ничего не
отправляет: следующий цикл бота (раз в час) пришлёт одно уведомление по всему
диапазону со всеми коммитами.

По умолчанию — пробный прогон: проверки и что будет объявлено, без записи.

Запуск (на сервере, из каталога бота):
    uv run python scripts/schematron_backfill.py --semd 289 --kind xsd --since c682b1e3
    uv run python scripts/schematron_backfill.py --semd 289 --kind xsd --since c682b1e3 \\
        --force --apply

--force нужен, если baseline уже есть (бот после деплоя зафиксировал текущую
версию тихо).
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config import get_config
from plugins.schematron_monitor.backfill import (
    BackfillError,
    apply_backfill,
    prepare_backfill,
)
from plugins.schematron_monitor.monitor import (
    ARTIFACT_KINDS,
    SchematronMonitor,
)
from plugins.semd_checker.semd_logic import get_semd638, get_semd1520
from services.gitlab_client import GitLabClient
from services.schematron_store import SchematronStore

KINDS = {kind.key: kind for kind in ARTIFACT_KINDS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--semd", required=True, help="OID СЭМД из 1520, например 289")
    parser.add_argument("--kind", required=True, choices=sorted(KINDS))
    parser.add_argument(
        "--since", required=True, help="коммит, ПОСЛЕ которого объявлять изменения"
    )
    parser.add_argument(
        "--force", action="store_true", help="перезаписать существующий baseline"
    )
    parser.add_argument(
        "--apply", action="store_true", help="записать (без флага — пробный прогон)"
    )
    return parser.parse_args()


def main() -> int:
    """Validate and optionally apply a baseline backfill."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    args = parse_args()
    config = get_config()

    client = GitLabClient.from_config(config)
    store = SchematronStore(config.paths.fnsi_db_path)
    monitor = SchematronMonitor(
        client=client,
        store=store,
        semd_lookup=get_semd1520().get_semd_info,
        notify=lambda change: None,
        package_lookup=get_semd638().get_git_link,
    )

    try:
        plan = prepare_backfill(
            monitor, args.semd, KINDS[args.kind], args.since, args.force
        )
    except BackfillError as e:
        print(f"Отказ: {e}")
        return 1

    prev = plan.previous
    print(f"СЭМД {plan.semd_oid} ({plan.kind.key}): {plan.repo.key}")
    print(
        "Сейчас:   "
        + (
            f"{prev.last_sha} ({prev.status}, проверка {prev.last_checked})"
            if prev
            else "нет записи"
        )
    )
    print(f"Станет:   {plan.since_sha}")
    print(f"Голова:   {plan.head['id']}")
    print(f"Следующий цикл объявит одним сообщением коммитов: {len(plan.commits)}")
    for commit in plan.commits:
        print(
            f"  {commit['id'][:8]} {commit.get('committed_date', '')[:10]} {commit.get('title', '')}"
        )

    if not args.apply:
        print("Пробный прогон — ничего не записано. Добавьте --apply для записи.")
        return 0
    apply_backfill(store, plan)
    print("Baseline записан. Уведомление придёт в следующем цикле бота.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

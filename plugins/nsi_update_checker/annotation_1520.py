"""
Annotation for updates of dictionary 1520 (registry of SEMD, «ЭМД»).

Builds "what changed" for one release from the FNSI API:
    * /versions — the immediate predecessor of the release and both publish dates;
    * /compare between those dates — records of the release with ``operation``
      (verified: lower bound exclusive, upper inclusive, records in the state of
      the release, net state when an interval spans several releases);
    * /data of the predecessor — old values of UPDATE records.

Only facts the data proves are stated ("a link to the guide was added", not
"the guide was published"). Anything the annotator does not fully understand
(an unknown operation, a changed field set, an ambiguous pair, missing old row)
raises AnnotationUnavailable: the caller then sends the plain notification.
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

OID_1520 = "1.2.643.5.1.13.13.11.1520"
KEY = "OID"
SUPPORTED_OPERATIONS = {"INSERT", "UPDATE"}
SERVICE_FIELDS = {"operation"}
DATE_FIELDS = {"START_DATE", "END_DATE"}
MAX_UPDATES = 80  # each UPDATE costs one /data request
VERSIONS_PAGE = 50
COMPARE_PAGE_SIZE = 200
MAX_COMPARE_PAGES = 5
# Official column titles from the 1520 passport (/passport → fields[].alias)
FIELD_TITLES = {
    "NAME": "Наименование",
    "TYPE": "Вид МД",
    "FORMAT": "Формат файла",
    "START_DATE": "Дата начала регистрации",
    "END_DATE": "Дата окончания регистрации",
    "GIT_LINK": "Идентификатор руководства по реализации СЭМД",
    "IMPLEMENTATION_GUIDE": "Ссылка на руководство по реализации СЭМД",
    "SHOW_PATIENT": "Доступен на ЕПГУ",
    "IS_ONLINE": "Доступен к заказу онлайн",
    "STORAGE_TYPE": "Тип хранения",
    "SHELF_LIFE": "Срок хранения",
    "EXTENDED_LIFE": "Допускается увеличение сроков хранения",
    "UNLIMITED_LIFE": "В том числе неограниченное увеличение сроков хранения",
    "PATIENT_INFO": "Сведения о пациенте",
    "MO_SIGN": "Необходима подпись МО",
    "SERIES_REQUIRED": "Серия документа",
    "DAYS_COUNT": "Срок предоставления",
    "LEVEL": "Уровень детализации",
    "ID": "Уникальный идентификатор",
}
LIST_LIMITS = (12, 6, 3, 0)  # items shown per list, shrunk until the text fits

ApiGet = Callable[..., dict]


class AnnotationUnavailable(Exception):
    """The release cannot be annotated completely; send the plain notification."""


@dataclass(frozen=True)
class Annotation:
    predecessor: str
    html: str


# ---------------------------------------------------------------- data access


def _parse_publish(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%d.%m.%Y %H:%M")
    except (TypeError, ValueError) as e:
        raise AnnotationUnavailable(f"unknown publishDate format: {value!r}") from e


def find_pair(get: ApiGet, target_version: str) -> Tuple[dict, dict]:
    """Return (predecessor, target) entries of /versions (newest first)."""
    versions = get("versions", page=1, size=VERSIONS_PAGE).get("list") or []
    index = next(
        (i for i, v in enumerate(versions) if v.get("version") == target_version), None
    )
    if index is None:
        raise AnnotationUnavailable(f"version {target_version} not in /versions")
    if index + 1 >= len(versions):
        raise AnnotationUnavailable(f"no predecessor for {target_version}")
    target, predecessor = versions[index], versions[index + 1]
    if _parse_publish(predecessor.get("publishDate")) >= _parse_publish(
        target.get("publishDate")
    ):
        # equal (or reversed) timestamps cannot identify the release by dates
        raise AnnotationUnavailable(
            f"ambiguous publish dates {predecessor.get('version')}→{target_version}"
        )
    return predecessor, target


def fetch_changes(get: ApiGet, predecessor: dict, target: dict) -> List[dict]:
    """All /compare records of the release, checked for completeness."""
    date1 = _parse_publish(predecessor["publishDate"]).strftime("%Y-%m-%d %H:%M")
    date2 = _parse_publish(target["publishDate"]).strftime("%Y-%m-%d %H:%M")
    rows: List[dict] = []
    total = None
    for page in range(1, MAX_COMPARE_PAGES + 1):
        data = get(
            "compare", date1=date1, date2=date2, page=page, size=COMPARE_PAGE_SIZE
        )
        payload = data.get("data")
        if not isinstance(payload, dict) or not isinstance(payload.get("list"), list):
            raise AnnotationUnavailable("compare: no data.list in the response")
        chunk = payload["list"]
        total = payload.get("total")
        rows.extend(chunk)
        if total is None or len(rows) >= total or len(chunk) < COMPARE_PAGE_SIZE:
            break
    if not rows:
        # an explicit empty list is not a "complete diff without changes":
        # the release does have changes, the interval just did not return them
        raise AnnotationUnavailable("compare returned no records for the release")
    if total is not None and len(rows) != total:
        raise AnnotationUnavailable(f"compare incomplete: {len(rows)} of {total}")
    return rows


def fetch_old_row(get: ApiGet, version: str, oid: str) -> dict:
    data = get("data", version=version, filters=f"{KEY}|{oid}|EQ", page=1, size=2)
    found = data.get("list") or []
    if len(found) != 1:
        raise AnnotationUnavailable(f"{KEY} {oid} in {version}: {len(found)} rows")
    return {cell["column"]: cell["value"] for cell in found[0]}


# ------------------------------------------------------------- normalisation


def _norm(field: str, value) -> Optional[str]:
    """Comparable value: dates as ISO (both API formats), empty as None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if field in DATE_FIELDS:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(str(value), fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        raise AnnotationUnavailable(f"unknown date format in {field}: {value!r}")
    return str(value).strip()


def _ru_date(iso: Optional[str]) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y") if iso else "—"


def _short_name(name: str) -> str:
    return re.sub(r"\s*Редакция\s+(\S+)\s*$", r" ред. \1", (name or "").strip())


def _oid_list(oids: List[str]) -> str:
    """Sorted OIDs, consecutive runs of 3+ collapsed: 340–344."""
    nums = sorted(int(o) for o in oids)
    parts, start = [], nums[0]
    for prev, cur in zip(nums, nums[1:] + [None]):
        if cur != prev + 1:
            if prev - start >= 2:
                parts.append(f"{start}–{prev}")
            else:
                parts.extend(str(n) for n in range(start, prev + 1))
            start = cur
    return ", ".join(parts)


# ---------------------------------------------------------------- diff → events


@dataclass(frozen=True)
class FieldChange:
    oid: str
    field: str
    old: Optional[str]
    new: Optional[str]
    name: str


def diff_update(new_row: dict, old_row: dict) -> List[FieldChange]:
    """Every field that differs between the predecessor and the release."""
    new_fields = set(new_row) - SERVICE_FIELDS
    if new_fields != set(old_row):
        raise AnnotationUnavailable(
            f"field set differs for {KEY} {new_row.get(KEY)}: "
            f"{sorted(new_fields ^ set(old_row))}"
        )
    changes = []
    for field in sorted(new_fields - {KEY}):
        old, new = _norm(field, old_row[field]), _norm(field, new_row[field])
        if old != new:
            changes.append(
                FieldChange(
                    str(new_row[KEY]), field, old, new, new_row.get("NAME") or ""
                )
            )
    return changes


def _listing(items: List[str], limit: int) -> str:
    shown = items[:limit]
    rest = len(items) - len(shown)
    body = "\n".join(shown) + (f"\n…и ещё {rest}" if rest else "")
    return f"<blockquote expandable>{body.strip()}</blockquote>" if body.strip() else ""


def _named(oid: str, name: str) -> str:
    return f"<b>{escape(oid)}</b> {escape(_short_name(name))}"


def render(inserts: List[dict], changes: List[FieldChange], limit: int) -> List[str]:
    """Events in priority order: new records, registration dates, guides, names, rest."""
    lines: List[str] = []

    by_start = defaultdict(list)
    for row in inserts:
        by_start[_norm("START_DATE", row.get("START_DATE"))].append(row)
    for start, rows in sorted(by_start.items(), key=lambda item: item[0] or ""):
        rows.sort(key=lambda r: int(r[KEY]))
        when = f", начало регистрации {_ru_date(start)}" if start else ""
        lines.append(f"➕ <b>Добавлены записи СЭМД ({len(rows)}){when}:</b>")
        lines.append(
            _listing([_named(str(r[KEY]), r.get("NAME")) for r in rows], limit)
        )

    grouped: Dict[Tuple[str, Optional[str], Optional[str]], List[FieldChange]] = (
        defaultdict(list)
    )
    for change in changes:
        grouped[(change.field, change.old, change.new)].append(change)

    def oids(group: List[FieldChange]) -> str:
        return _oid_list([c.oid for c in group])

    handled = set()
    for field in ("END_DATE", "START_DATE"):
        title = FIELD_TITLES[field].lower()
        for (f, old, new), group in sorted(grouped.items(), key=lambda g: str(g[0])):
            if f != field:
                continue
            if old is None:
                text = f"установлена {title} {_ru_date(new)}"
            elif new is None:
                text = f"снята {title} (была {_ru_date(old)})"
            else:
                text = f"{title} перенесена с {_ru_date(old)} на {_ru_date(new)}"
            lines.append(f"📅 <b>{text[0].upper() + text[1:]}:</b> {oids(group)}")
            handled.add((f, old, new))

    guides = {
        "added": "Добавлены ссылки на руководства по реализации",
        "replaced": "Заменены ссылки на руководства по реализации",
        "removed": "Убраны ссылки на руководства по реализации",
    }
    guide_groups = defaultdict(list)
    for (f, old, new), group in grouped.items():
        if f == "IMPLEMENTATION_GUIDE":
            kind = "added" if old is None else "removed" if new is None else "replaced"
            guide_groups[kind].extend(group)
            handled.add((f, old, new))
    for kind in ("added", "replaced", "removed"):
        group = sorted(guide_groups.get(kind, []), key=lambda c: int(c.oid))
        if not group:
            continue
        if kind == "removed":
            refs = oids(group)
        else:
            refs = ", ".join(
                f"<a href='{escape(c.new)}'>{escape(c.oid)}</a>" for c in group
            )
        lines.append(f"📘 <b>{guides[kind]}:</b> {refs}")

    names = sorted(
        (c for (f, _, _), group in grouped.items() if f == "NAME" for c in group),
        key=lambda c: int(c.oid),
    )
    if names:
        handled.update(k for k in grouped if k[0] == "NAME")
        lines.append(f"✏️ <b>Изменены наименования ({len(names)}):</b>")
        lines.append(
            _listing(
                [
                    f"<b>{escape(c.oid)}</b> {escape(_short_name(c.old or ''))} → "
                    f"{escape(_short_name(c.new or ''))}"
                    for c in names
                ],
                limit,
            )
        )

    # fields without a dedicated event: stated honestly, never dropped
    other = defaultdict(set)
    for key, group in grouped.items():
        if key not in handled:
            other[key[0]].update(c.oid for c in group)
    if other:
        parts = [
            f"«{escape(FIELD_TITLES.get(field, field))}» — {_oid_list(sorted(oids_))}"
            for field, oids_ in sorted(other.items())
        ]
        lines.append("ℹ️ <b>Также изменены другие поля:</b> " + "; ".join(parts))
    return [line for line in lines if line]


def build_1520_annotation(
    get: ApiGet, target_version: str, max_chars: int
) -> Annotation:
    """
    Build the "what changed" block for one release of 1520.

    Args:
        get: ``FnsiApi.get``-compatible callable (budgeted transport)
        target_version: the release being announced
        max_chars: room left in the message for this block (Telegram limit)

    Raises:
        AnnotationUnavailable: the release cannot be described completely.
    """
    predecessor, target = find_pair(get, target_version)
    rows = fetch_changes(get, predecessor, target)

    operations = {r.get("operation") for r in rows}
    if operations - SUPPORTED_OPERATIONS:
        raise AnnotationUnavailable(
            f"unsupported operations {sorted(map(str, operations - SUPPORTED_OPERATIONS))}"
        )
    keys = [str(r.get(KEY) or "").strip() for r in rows]
    if not all(keys) or len(set(keys)) != len(keys):
        raise AnnotationUnavailable(f"{KEY} is empty or not unique in compare")

    inserts = [r for r in rows if r["operation"] == "INSERT"]
    updates = [r for r in rows if r["operation"] == "UPDATE"]
    if len(updates) > MAX_UPDATES:
        raise AnnotationUnavailable(f"too many updates: {len(updates)}")
    changes: List[FieldChange] = []
    for row in updates:
        changes.extend(
            diff_update(row, fetch_old_row(get, predecessor["version"], row[KEY]))
        )
    if not inserts and not changes:
        raise AnnotationUnavailable("release has no visible changes")

    for limit in LIST_LIMITS:
        html = "\n".join(render(inserts, changes, limit))
        if len(html.encode("utf-16-le")) // 2 <= max_chars:
            return Annotation(predecessor["version"], html)
    raise AnnotationUnavailable("annotation does not fit the message")

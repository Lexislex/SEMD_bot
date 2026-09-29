"""Telegram message and .diff file formatting for schematron changes."""

from dataclasses import replace
from datetime import datetime
from html import escape
from typing import Dict, List, Optional, Set, Tuple

from .monitor import SchematronChange, is_diff_truncated

# Лимит Telegram — 4096 символов UTF-16 после разбора HTML; мы считаем по
# сырому HTML и держим запас
SAFE_MESSAGE_LIMIT = 4000
MAX_FILES_SHOWN = 15
# Короткий diff дополнительно вставляем в текст сообщения
INLINE_DIFF_LIMIT = 2500
MAX_COMMITS_SHOWN = 5


def tg_length(text: str) -> int:
    """Length in UTF-16 code units, as Telegram counts it."""
    return len(text.encode("utf-16-le")) // 2


def is_night(current_hour: Optional[int] = None) -> bool:
    """Night hours (22:00-08:00) — send notifications silently."""
    if current_hour is None:
        current_hour = datetime.now().hour
    return current_hour >= 22 or current_hour < 8


def diff_stats(diff_text: str) -> Tuple[int, int]:
    """Count added/removed lines of a unified diff hunk text."""
    added = removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def _format_date(iso_date: Optional[str]) -> str:
    if not iso_date:
        return ""
    try:
        return datetime.fromisoformat(iso_date).strftime("%d.%m.%Y")
    except ValueError:
        return iso_date[:10]


def _format_file_line(diff: Dict, attached: Set[str]) -> str:
    old_path, new_path = diff.get("old_path"), diff.get("new_path")
    if diff.get("new_file"):
        icon, name = "➕", escape(new_path)
    elif diff.get("deleted_file"):
        icon, name = "➖", escape(old_path)
    elif diff.get("renamed_file"):
        icon, name = "✏️", f"{escape(old_path)} → {escape(new_path)}"
    else:
        icon, name = "✏️", escape(new_path)

    if is_diff_truncated(diff):
        if diff.get("new_path") in attached:
            stats = " (diff слишком большой, новая версия приложена файлом)"
        else:
            stats = " (diff слишком большой, см. GitLab)"
    else:
        added, removed = diff_stats(diff.get("diff", ""))
        stats = f" (+{added} / −{removed})"
    return f"• {icon} {name}{stats}"


def _format_commit_line(change: SchematronChange, commit: Dict, client) -> str:
    sha = commit.get("id", "")
    short = commit.get("short_id") or sha[:8]
    link = (
        f"<a href='{escape(client.commit_url(change.repo, sha))}'>{escape(short)}</a>"
    )
    date = _format_date(commit.get("committed_date"))
    title = escape(commit.get("title") or "")
    return f"• {link} {date}: {title}"


def _format_commits(change: SchematronChange, client) -> List[str]:
    commits = change.commits  # свежие первыми
    lines = [
        _format_commit_line(change, c, client) for c in commits[:MAX_COMMITS_SHOWN]
    ]
    if len(commits) > MAX_COMMITS_SHOWN:
        lines.append(f"• …и ещё {len(commits) - MAX_COMMITS_SHOWN}")
    return lines


def _format_files(change: SchematronChange, max_files: int) -> List[str]:
    attached = {path for path, _ in change.attachments}
    lines = [_format_file_line(d, attached) for d in change.diffs[:max_files]]
    if len(change.diffs) > max_files:
        lines.append(f"• …и ещё {len(change.diffs) - max_files} (см. .diff)")
    return lines


def _render_message(change: SchematronChange, client, max_files: int) -> str:
    lines = [
        "🧩 <b>Изменён схематрон СЭМД</b>",
        "",
        f"<b>{escape(change.semd_name)}</b>",
        f"OID: <code>{escape(change.semd_oid)}</code> · "
        f"пакет <code>{escape(change.repo.git_link)}</code>",
        "",
    ]

    if change.history_rewritten:
        lines.append(
            "⚠️ История ветки в GitLab переписана: предыдущая отслеживаемая версия "
            f"(<code>{escape(change.from_sha[:8])}</code>) больше не существует, "
            "сравнение недоступно."
        )
    elif change.compare_timed_out:
        lines.append("⚠️ GitLab не успел построить сравнение, diff недоступен.")

    if change.history_rewritten or change.compare_timed_out:
        if change.attachments:
            lines.append("📎 Текущая версия схематрона приложена файлом.")
        commits = change.commits or [change.head_commit]
        lines += ["", "📝 <b>Коммиты:</b>"]
        lines += _format_commits(replace(change, commits=commits), client)
    else:
        lines.append("📄 <b>Файлы:</b>")
        lines += _format_files(change, max_files)
        lines += ["", "📝 <b>Коммиты:</b>"]
        lines += _format_commits(change, client)

    links = []
    if change.compare_url:
        links.append(f"<a href='{escape(change.compare_url)}'>Сравнение в GitLab</a>")
    if change.tree_url:
        links.append(f"<a href='{escape(change.tree_url)}'>Папка schematron</a>")
    if links:
        lines += ["", "🔗 " + " · ".join(links)]

    lines += ["", f"#схематрон #СЭМД_{escape(change.semd_oid)}"]
    return "\n".join(lines)


def format_change_message(change: SchematronChange, client) -> str:
    """Build HTML notification text (without inline diff).

    The file list is shortened until the message fits into one Telegram
    message; an oversized message would fail in every chat and block the
    baseline forever.
    """
    max_files = MAX_FILES_SHOWN
    while True:
        text = _render_message(change, client, max_files)
        if tg_length(text) <= SAFE_MESSAGE_LIMIT or max_files == 0:
            return text
        max_files = max_files // 2


def build_diff_text(change: SchematronChange) -> str:
    """Unified diff of schematron files with a short header."""
    parts = [
        f"# СЭМД {change.semd_oid}: {change.semd_name}",
        f"# {change.repo.project_path} @ {change.repo.ref}",
        f"# {change.from_sha}..{change.to_sha}",
    ]
    if change.compare_url:
        parts.append(f"# {change.compare_url}")
    parts.append("")

    for diff in change.diffs:
        old_path = "/dev/null" if diff.get("new_file") else f"a/{diff.get('old_path')}"
        new_path = (
            "/dev/null" if diff.get("deleted_file") else f"b/{diff.get('new_path')}"
        )
        parts.append(f"--- {old_path}")
        parts.append(f"+++ {new_path}")
        if is_diff_truncated(diff):
            parts.append(
                "# diff слишком большой, GitLab не вернул содержимое — см. сравнение в GitLab"
            )
        else:
            parts.append(diff.get("diff", "").rstrip("\n"))
        parts.append("")
    return "\n".join(parts)


def diff_file_name(change: SchematronChange) -> str:
    return (
        f"schematron_{change.semd_oid}_{change.from_sha[:8]}_{change.to_sha[:8]}.diff"
    )


def _collapsed_code(text: str) -> str:
    """Collapsed quote with monospace lines.

    <pre> inside <blockquote expandable> is not collapsed by mobile Telegram
    clients, so every line is wrapped in <code> instead.
    """
    lines = [
        f"<code>{escape(line)}</code>" if line else "" for line in text.splitlines()
    ]
    return "<blockquote expandable>" + "\n".join(lines) + "</blockquote>"


def with_inline_diff(message: str, change: SchematronChange) -> str:
    """Append a short diff to the message if it fits into one Telegram message."""
    if (
        change.history_rewritten
        or change.compare_timed_out
        or any(is_diff_truncated(d) for d in change.diffs)
    ):
        return message
    diff_body = "\n".join(d.get("diff", "").rstrip("\n") for d in change.diffs)
    if not diff_body or len(diff_body) > INLINE_DIFF_LIMIT:
        return message
    # Вставляем diff перед хэштегами, чтобы они оставались последней строкой
    body, sep, hashtags = message.rpartition("\n\n#")
    quote = _collapsed_code(diff_body)
    candidate = f"{body}\n\n{quote}{sep}{hashtags}" if sep else f"{message}\n\n{quote}"
    return candidate if tg_length(candidate) <= SAFE_MESSAGE_LIMIT else message

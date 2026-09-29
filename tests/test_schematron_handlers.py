import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plugins.schematron_monitor import handlers as handlers_module
from plugins.schematron_monitor.handlers import SchematronHandlers
from plugins.schematron_monitor.monitor import NotificationError, SchematronChange
from services.gitlab_client import GitLabClient, SemdRepo

SCH_DIFF = {
    "old_path": "schematron/331 v1.2.sch",
    "new_path": "schematron/331 v1.3.sch",
    "diff": "@@ -1 +1 @@\n-a\n+b\n",
    "new_file": False,
    "renamed_file": True,
    "deleted_file": False,
}


def make_change(**kwargs) -> SchematronChange:
    head = {
        "id": "b" * 40,
        "short_id": "bbbbbbbb",
        "title": "Обновление схематрона",
        "committed_date": "2026-09-07T11:46:40.000+00:00",
    }
    defaults = dict(
        semd_oid="331",
        semd_name="Направление (CDA) Редакция 4",
        repo=SemdRepo.from_git_link("1.2.643.5.1.13.13.15.33.4"),
        from_sha="a" * 40,
        to_sha="b" * 40,
        head_commit=head,
        commits=[head],
        diffs=[SCH_DIFF],
    )
    defaults.update(kwargs)
    return SchematronChange(**defaults)


def make_handlers(chats) -> SchematronHandlers:
    """SchematronHandlers without __init__ (no 1520 download, no GitLab)."""
    h = SchematronHandlers.__new__(SchematronHandlers)
    h.bot = MagicMock()
    h.config = SimpleNamespace(accounts=SimpleNamespace(updates_mailing_list=chats))
    h.logger = logging.getLogger("test")
    h.client = GitLabClient("https://git.example.ru", token="t")
    return h


def test_empty_mailing_list_raises():
    h = make_handlers([])
    with pytest.raises(NotificationError):
        h.send_change(make_change())
    h.bot.send_message.assert_not_called()


def test_sends_message_and_diff_to_every_chat():
    h = make_handlers([1, 2])
    h.send_change(make_change())

    assert [c.args[0] for c in h.bot.send_message.call_args_list] == [1, 2]
    docs = h.bot.send_document.call_args_list
    assert [c.args[0] for c in docs] == [1, 2]
    assert docs[0].kwargs["visible_file_name"].endswith(".diff")


def test_partial_delivery_is_success():
    h = make_handlers([1, 2])
    h.bot.send_message.side_effect = [RuntimeError("chat 1 down"), MagicMock()]

    h.send_change(make_change())  # не бросает

    # Файл отправлен только туда, где ушёл текст
    assert [c.args[0] for c in h.bot.send_document.call_args_list] == [2]


def test_zero_delivery_raises():
    h = make_handlers([1, 2])
    h.bot.send_message.side_effect = RuntimeError("telegram down")
    with pytest.raises(NotificationError):
        h.send_change(make_change())


def test_document_failure_does_not_block_delivery():
    h = make_handlers([1])
    h.bot.send_document.side_effect = RuntimeError("file rejected")
    h.send_change(make_change())  # текст доставлен — baseline можно сдвигать


def test_attachments_sent_by_basename():
    h = make_handlers([1])
    change = make_change(
        diffs=[],
        history_rewritten=True,
        attachments=[("schematron/40 v1.2.sch", b"<schema/>")],
    )
    h.send_change(change)

    docs = h.bot.send_document.call_args_list
    assert [c.kwargs["visible_file_name"] for c in docs] == ["40 v1.2.sch"]


def test_oversized_document_skipped(monkeypatch):
    monkeypatch.setattr(handlers_module, "MAX_DOCUMENT_BYTES", 10)
    h = make_handlers([1])
    change = make_change(attachments=[("schematron/big.sch", b"x" * 11)])
    h.send_change(change)

    names = [c.kwargs["visible_file_name"] for c in h.bot.send_document.call_args_list]
    assert "big.sch" not in names
    h.bot.send_message.assert_called_once()

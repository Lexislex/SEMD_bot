from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from telebot import apihelper

from core.bot import SEMDBotCore, send_params_in_body


@pytest.fixture
def session():
    mock = MagicMock()
    with patch.object(apihelper, "_get_req_session", return_value=mock):
        yield mock


def test_post_params_go_to_body(session):
    params = {"chat_id": 1, "text": "Протокол " * 1000}

    send_params_in_body(
        "post", "https://proxy/botT/sendMessage", params=params, timeout=(5, 30)
    )

    args, kwargs = session.request.call_args
    assert args == ("post", "https://proxy/botT/sendMessage")
    assert kwargs["data"] == params
    assert "params" not in kwargs
    assert kwargs["timeout"] == (5, 30)


def test_post_with_files_keeps_fields_in_multipart(session):
    files = {"document": ("a.diff", b"x")}

    send_params_in_body("post", "u", params={"chat_id": 1}, files=files)

    kwargs = session.request.call_args.kwargs
    assert kwargs["data"] == {"chat_id": 1}
    assert kwargs["files"] is files


def test_get_keeps_query_params(session):
    send_params_in_body("get", "u", params={"offset": 5})

    kwargs = session.request.call_args.kwargs
    assert kwargs["params"] == {"offset": 5}
    assert "data" not in kwargs


def test_long_text_is_not_in_url():
    """The prepared request URL stays short for a 4000-char Cyrillic text."""
    text = "Изменена XSD-схема СЭМД " * 170
    with patch.object(apihelper, "_get_req_session", return_value=requests.Session()):
        with patch.object(requests.Session, "send") as send:
            send.return_value = MagicMock()
            send_params_in_body(
                "post", "https://proxy/botT/sendMessage", params={"text": text}
            )
    prepared = send.call_args.args[0]
    assert prepared.url == "https://proxy/botT/sendMessage"
    assert len(prepared.body) > 8 * 1024


def test_sender_installed():
    config = SimpleNamespace(
        proxy=SimpleNamespace(enabled=False, host=None, port=None),
        app=SimpleNamespace(telegram_api_base_url=None),
    )
    with patch.object(apihelper, "CUSTOM_REQUEST_SENDER", None):
        SEMDBotCore._apply_telegram_api_settings(config)
        assert apihelper.CUSTOM_REQUEST_SENDER is send_params_in_body

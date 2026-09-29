import pytest

from plugins.nsi_update_checker.data import NSI_DICTIONARIES, notified_count
from plugins.nsi_update_checker.formatters import (
    DefaultUpdateFormatter,
    ImportantUpdateFormatter,
    MinorUpdateFormatter,
)

FNSI_INFO = {
    "id": "1.2.643.5.1.13.13.11.1520",
    "fullName": "Электронные медицинские документы",
    "shortName": "ЭМД <R&D>",
    "lastUpdate": "2026-09-15T15:27:00",
    "version": "12.96",
    "releaseNotes": "Добавлено: 2; Изменено: <3>;",
}


@pytest.mark.parametrize(
    "formatter, title",
    [
        (ImportantUpdateFormatter(), "Важное обновление"),
        (DefaultUpdateFormatter(), "Обновление справочника"),
    ],
)
def test_full_formatter_escapes_fnsi_data(formatter, title):
    message = formatter.format(FNSI_INFO, FNSI_INFO["id"])

    assert title in message
    assert "ЭМД &lt;R&amp;D&gt;" in message
    assert "Изменено: &lt;3&gt;" in message
    assert "<R&D>" not in message
    assert "passport/12.96" in message
    assert "#сен2026" in message


def test_minor_formatter_escapes_fnsi_data():
    message = MinorUpdateFormatter().format(FNSI_INFO)
    assert "<b>ЭМД &lt;R&amp;D&gt;</b> v12.96" in message


def test_hashtags_survive_bad_date():
    tags = DefaultUpdateFormatter().get_hashtags(
        dict(FNSI_INFO, lastUpdate="not a date"), FNSI_INFO["id"]
    )
    assert tags == "#ЭМД__R_D_"


def test_notified_count_skips_silent_dictionaries():
    assert NSI_DICTIONARIES["1.2.643.5.1.13.13.99.2.638"]["notify"] is False
    assert notified_count() == len(NSI_DICTIONARIES) - sum(
        1 for p in NSI_DICTIONARIES.values() if not p.get("notify", True)
    )
    assert notified_count() < len(NSI_DICTIONARIES)

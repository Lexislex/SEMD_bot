from unittest.mock import MagicMock, patch

import pytest

from utils import file_utils

OID = "1.2.643.5.1.13.13.99.2.63"


@pytest.fixture
def files(tmp_path):
    for name in [
        f"{OID}_1.0_csv.zip",  # старая версия — удалить
        f"{OID}8_7.75_csv.zip",  # другой справочник (...2.638) — не трогать
        "other_1.0_csv.zip",
    ]:
        (tmp_path / name).write_bytes(b"old")
    return tmp_path


@pytest.fixture
def cert(tmp_path):
    cert = tmp_path / "cert.crt"
    cert.write_text("cert")
    cfg = MagicMock()
    cfg.paths.mzrf_cert_path = cert
    cfg.apis.fnsi_files_url = "https://nsi.example.ru/files/"
    cfg.apis.fnsi_request_timeout = 42
    with (
        patch.object(file_utils, "cfg", cfg),
        patch.object(file_utils, "build_proxies", return_value=None),
    ):
        yield cert


def _response(status=200, body=b"new"):
    resp = MagicMock(status_code=status)
    resp.iter_content.return_value = [body]
    resp.json.return_value = {"resultText": "not found"}
    return resp


def test_download_replaces_old_versions_of_same_dictionary(files, cert):
    with patch.object(file_utils.requests, "get", return_value=_response()) as get:
        assert file_utils.download_file(OID, "2.0", path=files)

    assert sorted(p.name for p in files.glob("*.zip")) == [
        f"{OID}8_7.75_csv.zip",
        f"{OID}_2.0_csv.zip",
        "other_1.0_csv.zip",
    ]
    assert (files / f"{OID}_2.0_csv.zip").read_bytes() == b"new"
    assert get.call_args.kwargs["timeout"] == 42


def test_failed_download_keeps_old_version(files, cert):
    with patch.object(file_utils.requests, "get", return_value=_response(404)):
        assert not file_utils.download_file(OID, "2.0", path=files)

    assert (files / f"{OID}_1.0_csv.zip").exists()
    assert not (files / f"{OID}_2.0_csv.zip").exists()


def test_existing_file_is_not_downloaded(files, cert):
    with patch.object(file_utils.requests, "get") as get:
        assert file_utils.download_file(OID, "1.0", path=files)
    get.assert_not_called()

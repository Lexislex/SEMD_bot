from unittest.mock import MagicMock, patch

import pytest
import requests

from services.gitlab_client import (
    GitLabAuthError,
    GitLabClient,
    GitLabError,
    GitLabNotFoundError,
    SemdRepo,
)


def _response(status: int, json_data=None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.headers = {}
    return resp


@pytest.fixture
def client() -> GitLabClient:
    return GitLabClient("https://git.example.ru/", token="t", max_retries=3)


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("services.gitlab_client.sleep"):
        yield


REPO = SemdRepo.from_git_link("1.2.643.5.1.13.13.15.33.4")


class TestSemdRepo:
    def test_from_git_link(self):
        assert REPO.project_path == "semd/1.2.643.5.1.13.13.15.33"
        assert REPO.ref == "1.2.643.5.1.13.13.15.33.4"
        assert REPO.git_link == "1.2.643.5.1.13.13.15.33.4"

    def test_strips_whitespace(self):
        repo = SemdRepo.from_git_link("  1.2.643.5.1.13.13.15.110.2 ")
        assert repo.project_path == "semd/1.2.643.5.1.13.13.15.110"

    @pytest.mark.parametrize("value", ["", None, "abc", "1.2.643.x", "https://git/x"])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            SemdRepo.from_git_link(value)

    def test_key(self):
        assert REPO.key == "semd/1.2.643.5.1.13.13.15.33@1.2.643.5.1.13.13.15.33.4"

    @pytest.mark.parametrize(
        "url",
        [
            "https://git.minzdrav.gov.ru/semd/1.2.643.5.1.13.13.15.35/-/tree/"
            "1.2.643.5.1.13.13.15.35.5",
            # так в 638 записана ссылка СЭМД 321
            " https://git.minzdrav.gov.ru/semd/1.2.643.5.1.13.13.15.35/-/blob/"
            "1.2.643.5.1.13.13.15.35.5/ ",
        ],
    )
    def test_from_url(self, url):
        repo = SemdRepo.from_url(url, "1.2.643.5.1.13.13.15.36.5")
        assert repo.project_path == "semd/1.2.643.5.1.13.13.15.35"
        assert repo.ref == "1.2.643.5.1.13.13.15.35.5"
        assert repo.git_link == "1.2.643.5.1.13.13.15.36.5"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            None,
            "https://git.minzdrav.gov.ru/semd/1.2.643.5.1.13.13.15.35",
            "https://git.minzdrav.gov.ru/-/tree/1.2.643.5.1.13.13.15.35.5",
            "https://git.minzdrav.gov.ru/semd/1.2.643.5.1.13.13.15.35/-/tree/",
        ],
    )
    def test_from_url_invalid(self, url):
        with pytest.raises(ValueError):
            SemdRepo.from_url(url, "1.2.643.5.1.13.13.15.36.5")


class TestClient:
    def test_requires_token(self):
        with pytest.raises(GitLabAuthError):
            GitLabClient("https://git.example.ru", token="")

    def test_urls(self, client):
        assert (
            client.project_url(REPO)
            == "https://git.example.ru/semd/1.2.643.5.1.13.13.15.33"
        )
        assert client.compare_url(REPO, "a", "b").endswith("/-/compare/a...b")
        assert client.tree_url(REPO, "schematron").endswith(
            "/-/tree/1.2.643.5.1.13.13.15.33.4/schematron"
        )

    def test_last_commit(self, client):
        commit = {"id": "abc"}
        with patch.object(
            client.session, "get", return_value=_response(200, [commit])
        ) as get:
            assert client.get_last_commit(REPO, path="schematron") == commit
        url = get.call_args.args[0]
        assert url == (
            "https://git.example.ru/api/v4/projects/"
            "semd%2F1.2.643.5.1.13.13.15.33/repository/commits"
        )
        assert get.call_args.kwargs["params"] == {
            "ref_name": REPO.ref,
            "per_page": 1,
            "path": "schematron",
        }

    def test_last_commit_empty_existing_branch(self, client):
        responses = [_response(200, []), _response(200, {"name": REPO.ref})]
        with patch.object(client.session, "get", side_effect=responses):
            assert client.get_last_commit(REPO, path="schematron") is None

    def test_last_commit_missing_branch(self, client):
        # GitLab отдаёт [] для несуществующей ветки, 404 — на запрос самой ветки
        responses = [_response(200, []), _response(404, {"message": "404"})]
        with (
            patch.object(client.session, "get", side_effect=responses),
            pytest.raises(GitLabNotFoundError),
        ):
            client.get_last_commit(REPO, path="schematron")

    def test_retry_on_5xx_then_success(self, client):
        responses = [_response(502), _response(200, [{"id": "x"}])]
        with patch.object(client.session, "get", side_effect=responses) as get:
            assert client.get_last_commit(REPO)["id"] == "x"
        assert get.call_count == 2

    def test_retry_on_timeout_exhausted(self, client):
        with (
            patch.object(
                client.session, "get", side_effect=requests.exceptions.Timeout("slow")
            ) as get,
            pytest.raises(GitLabError),
        ):
            client.get_last_commit(REPO)
        assert get.call_count == 3

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_error_no_retry(self, client, status):
        with (
            patch.object(client.session, "get", return_value=_response(status)) as get,
            pytest.raises(GitLabAuthError),
        ):
            client.compare(REPO, "a", "b")
        assert get.call_count == 1

    def test_compare_missing_commit(self, client):
        with (
            patch.object(client.session, "get", return_value=_response(404)),
            pytest.raises(GitLabNotFoundError),
        ):
            client.compare(REPO, "gone", "b")

    def test_list_files_paginates(self, client):
        page1 = [{"type": "blob", "path": f"schematron/{i}.sch"} for i in range(100)]
        page2 = [
            {"type": "tree", "path": "schematron/sub"},
            {"type": "blob", "path": "schematron/x.sch"},
        ]
        with patch.object(
            client.session,
            "get",
            side_effect=[_response(200, page1), _response(200, page2)],
        ) as get:
            files = client.list_files(REPO, "schematron", "sha")
        assert len(files) == 101 and files[-1] == "schematron/x.sch"
        assert get.call_args.kwargs["params"]["page"] == 2

    def test_get_raw_file(self, client):
        resp = _response(200)
        resp.content = b"<schema/>"
        with patch.object(client.session, "get", return_value=resp) as get:
            assert (
                client.get_raw_file(REPO, "schematron/331 v1.3.sch", "sha")
                == b"<schema/>"
            )
        assert get.call_args.args[0].endswith(
            "/repository/files/schematron%2F331%20v1.3.sch/raw"
        )
        assert get.call_args.kwargs["params"] == {"ref": "sha"}

    def test_retry_on_429_honors_retry_after(self, client):
        throttled = _response(429)
        throttled.headers = {"Retry-After": "7"}
        with (
            patch.object(
                client.session,
                "get",
                side_effect=[throttled, _response(200, [{"id": "x"}])],
            ) as get,
            patch("services.gitlab_client.sleep") as sleep,
        ):
            assert client.get_last_commit(REPO)["id"] == "x"
        assert get.call_count == 2
        sleep.assert_called_once_with(7)

    def test_list_commits_range_and_path(self, client):
        with patch.object(
            client.session, "get", return_value=_response(200, [{"id": "b"}])
        ) as get:
            assert client.list_commits(REPO, "a", "b", path="schematron") == [
                {"id": "b"}
            ]
        assert get.call_args.kwargs["params"] == {
            "ref_name": "a..b",
            "per_page": 100,
            "path": "schematron",
        }

"""Every tool funnels failures through handle_api_error, so its branches are
the error contract for the whole server."""
import httpx
import pytest

from utils.http import handle_api_error


def _status_error(code):
    return httpx.HTTPStatusError(
        "boom",
        request=httpx.Request("GET", "https://example.test"),
        response=httpx.Response(code),
    )


@pytest.mark.parametrize(
    "code,fragment",
    [(404, "not found"), (429, "rate limit"), (403, "access denied"), (500, "status 500")],
)
def test_http_status_errors_map_to_plain_english(code, fragment):
    assert fragment in handle_api_error(_status_error(code)).lower()


def test_timeout_is_reported_as_a_timeout():
    assert "timed out" in handle_api_error(httpx.TimeoutException("slow")).lower()


def test_unexpected_errors_keep_their_type_for_debugging():
    assert "ValueError" in handle_api_error(ValueError("bad json"))


def test_every_error_path_returns_a_string():
    for exc in (_status_error(404), httpx.TimeoutException("x"), RuntimeError("y")):
        assert isinstance(handle_api_error(exc), str)

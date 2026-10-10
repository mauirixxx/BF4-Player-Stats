"""Offline redirect mock: no DNS, sockets, HTTP or DB."""
from bf4ps.dispatch_urllib_redirect_mock import simulated_fetch


def test_default_redirect_causes_second_logical_http_open():
    paths, status = simulated_fetch(allow_redirects=True)
    assert status == 200
    assert paths == [
        "https://battlelog.invalid/initial",
        "https://battlelog.invalid/redirected",
    ]


def test_redirect_refusal_limits_handler_to_one_open():
    paths, status = simulated_fetch(allow_redirects=False)
    assert status == 302
    assert paths == ["https://battlelog.invalid/initial"]


def test_redirects_have_distinct_logical_attempt_cost():
    redirected, _ = simulated_fetch(allow_redirects=True)
    blocked, _ = simulated_fetch(allow_redirects=False)
    assert len(redirected) == 2
    assert len(blocked) == 1

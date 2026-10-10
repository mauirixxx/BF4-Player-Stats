"""No-network checks of default urllib opener policy."""
from bf4ps.dispatch_urllib_policy_inspection import (
    default_proxy_handler_present,
    default_redirect_handler_present,
    redirect_statuses_supported,
)


def test_default_opener_has_redirect_handler():
    assert default_redirect_handler_present()


def test_redirect_codes_are_supported_by_default_handler():
    assert {301, 302, 303, 307, 308}.issubset(redirect_statuses_supported())


def test_default_opener_proxy_handler_is_environment_dependent():
    # urllib may omit the handler when no proxies are configured. The presence
    # or absence of this handler on tcou is not a host-wide egress guarantee.
    assert isinstance(default_proxy_handler_present(), bool)

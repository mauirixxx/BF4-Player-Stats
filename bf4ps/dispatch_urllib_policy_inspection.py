"""Offline urllib transport policy inspection, no network access.

These checks use Python's local handler objects only. They never build an
opener that performs HTTP and never contact Battlelog.
"""
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


def default_redirect_handler_present() -> bool:
    opener = build_opener()
    return any(isinstance(handler, HTTPRedirectHandler) for handler in opener.handlers)


def redirect_statuses_supported() -> tuple[int, ...]:
    handler = HTTPRedirectHandler()
    return tuple(
        status for status in (301, 302, 303, 307, 308)
        if hasattr(handler, f"http_error_{status}")
    )


def default_proxy_handler_present() -> bool:
    opener = build_opener()
    return any(isinstance(handler, ProxyHandler) for handler in opener.handlers)

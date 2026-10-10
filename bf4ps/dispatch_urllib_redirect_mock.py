"""Offline urllib redirect counterexample using in-memory handler responses.

The fake transport never opens sockets. Its counters represent *logical HTTP
handler invocations*, not proof of physical packets or remote receipt.
"""
from __future__ import annotations

from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import BaseHandler, HTTPHandler, HTTPRedirectHandler, Request, build_opener, addinfourl


class FakeHTTPHandler(HTTPHandler):
    handler_order = 100

    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def http_open(self, request: Request):
        self.paths.append(request.full_url)
        if request.full_url.endswith("/initial"):
            headers = Message()
            headers["Location"] = "https://battlelog.invalid/redirected"
            headers["Content-Type"] = "text/plain"
            return addinfourl(BytesIO(b""), headers, request.full_url, code=302)
        headers = Message()
        headers["Content-Type"] = "application/json"
        return addinfourl(BytesIO(b"{}"), headers, request.full_url, code=200)

    https_open = http_open


class RefuseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def simulated_fetch(*, allow_redirects: bool) -> tuple[list[str], int]:
    handler = FakeHTTPHandler()
    opener = build_opener(handler, *([] if allow_redirects else [RefuseRedirect()]))
    try:
        with opener.open("https://battlelog.invalid/initial") as response:
            return handler.paths, response.status
    except HTTPError as exc:
        return handler.paths, exc.code

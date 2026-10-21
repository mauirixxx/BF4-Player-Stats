"""One-request urllib transport: HTTP redirects never create hidden requests.

Each invocation performs at most one physical HTTP request. Redirect responses
are returned as HTTPError so the caller may classify them as failures. Any
future explicit redirect follow must acquire a new physical dispatch permit.
"""
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_RejectRedirect)


def single_request_urlopen(request: Request, *, timeout: float):
    """Open exactly one request; no automatic HTTP redirect following."""
    return _OPENER.open(request, timeout=timeout)

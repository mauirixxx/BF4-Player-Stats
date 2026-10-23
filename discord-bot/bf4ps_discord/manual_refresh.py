"""Authenticated, bounded client for the existing private manual-refresh API."""
import asyncio
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PLATFORMS = {"pc": "pc", "ps4": "ps4", "xboxone": "xboxone"}

def _request(persona_id: int, platform: str, name: str):
    endpoint = os.environ.get("BF4PS_REFRESH_API_URL", "")
    token = os.environ.get("BF4PS_REFRESH_API_TOKEN", "")
    origin = os.environ.get("BF4PS_REFRESH_API_ORIGIN", "https://bf4playerstats.com")
    if not endpoint or not token or len(token) < 32:
        raise RuntimeError("Refresh service is not configured")
    if not endpoint.startswith("http://127.0.0.1:"):
        raise RuntimeError("Refresh service must use a local authenticated tunnel")
    if platform not in PLATFORMS or not 0 < int(persona_id) < 2**63:
        raise ValueError("Invalid player identity")
    url = ("https://battlelog.battlefield.com/bf4/soldier/"
           + quote(name, safe="") + "/stats/" + str(persona_id) + "/" + platform + "/")
    body = json.dumps({"url": url, "kind": "refresh"}).encode("utf-8")
    req = Request(endpoint, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Origin": origin,
        "X-BF4PS-Private-Token": token,
    })
    try:
        with urlopen(req, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            result = json.load(exc)
        except Exception:
            result = {}
        if exc.code in (404, 429):
            return result
        raise RuntimeError("Refresh backend rejected the request") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Refresh backend is unreachable") from exc

async def request_refresh(persona_id: int, platform: str, name: str):
    return await asyncio.wait_for(
        asyncio.to_thread(_request, persona_id, platform, name), timeout=12)

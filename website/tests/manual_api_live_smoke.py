#!/usr/bin/env python3
"""Opt-in HTTP-to-PostgreSQL smoke test against an isolated scratch database.

Requires a separately provisioned restricted LOGIN and scratch soldier.
Credentials come exclusively from the process environment; never from CLI.
"""
import http.client
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from manual_request_api import Handler, SlidingWindowLimiter

SOLDIER_URL = ("https://battlelog.battlefield.com/bf4/soldier/"
               "scratch-only/stats/876543210/pc/")

def run():
    dsn = os.environ.get("BF4PS_MANUAL_SMOKE_DATABASE_URL", "")
    token = os.environ.get("BF4PS_MANUAL_SMOKE_TOKEN", "")
    if not dsn or len(token) < 32:
        raise SystemExit("Missing smoke DSN or 32+ character token")
    url = make_url(dsn)
    if not (url.database and url.database.startswith("bf4ps_manual_")
            and url.database.endswith("_scratch")):
        raise SystemExit("Refusing to connect to non-scratch database")
    if url.username != "bf4ps_manual_e2e_api":
        raise SystemExit("Refusing to use a non-restricted login")
    engine = create_engine(dsn, pool_pre_ping=True, pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            who = conn.execute(text("SELECT current_user")).scalar_one()
            privileges = conn.execute(text("""
                SELECT has_table_privilege(current_user,
                           'public.collection_jobs','INSERT'),
                       has_table_privilege(current_user,
                           'public.soldiers','UPDATE'),
                       has_function_privilege(current_user,
                           'manual_api.request_existing_soldier(bigint,text,text)',
                           'EXECUTE')
            """)).one()
            if who != "bf4ps_manual_e2e_api" or tuple(privileges) != (False, False, True):
                raise AssertionError("Restricted API role permissions are incorrect")
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.engine = engine
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.dict(os.environ, {
                "BF4PS_MANUAL_PRIVATE_TOKEN": token,
                "BF4PS_MANUAL_ALLOWED_ORIGIN": "https://bf4playerstats.com",
            }), patch("manual_request_api.LIMITER", SlidingWindowLimiter()):
                observed = []
                for _ in range(2):
                    client = http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=10)
                    client.request("POST", "/manual/request",
                                   json.dumps({"url": SOLDIER_URL, "kind": "refresh"}),
                                   {"X-BF4PS-Private-Token": token,
                                    "Origin": "https://bf4playerstats.com",
                                    "Content-Type": "application/json"})
                    response = client.getresponse()
                    body = json.loads(response.read())
                    observed.append((response.status, body.get("state"),
                                     body.get("jobs_created")))
                    client.close()
                expected = [(202, "accepted", 4), (200, "cooldown", 0)]
                if observed != expected:
                    raise AssertionError(f"Unexpected HTTP results: {observed}")
                # This API login intentionally has no direct table SELECT rights.
                # Confirm denial instead of querying collection_jobs as the API.
                with engine.connect() as conn:
                    try:
                        conn.execute(text("SELECT count(*) FROM public.collection_jobs"))
                    except Exception as exc:
                        if getattr(getattr(exc, "orig", None), "sqlstate", None) != "42501":
                            raise
                    else:
                        raise AssertionError("API login unexpectedly has direct job-table SELECT")
                print("PASS: restricted login, HTTP admission, cooldown, four jobs reported; direct SELECT denied")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
    finally:
        engine.dispose()

if __name__ == "__main__":
    run()

"""Join the verified soldier fetch to transactional admission."""
from bf4ps.manual_battlelog_verification import fetch_verified_soldier
from bf4ps.manual_verified_ingestion import insert_verified_manual_soldier


def add_verified_soldier(engine, url, dispatch_context):
    verified = fetch_verified_soldier(url, authorized_dispatch=dispatch_context)
    with engine.begin() as conn:
        return insert_verified_manual_soldier(conn, url=url, verified=verified)

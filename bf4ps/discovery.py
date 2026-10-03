from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from bf4ps.config import database_url

SOURCE_NAME = "bf4sw"
RECONCILE_SOURCE_NAME = "bf4sw_reconcile"
DEFAULT_BATCH_SIZE = 100
DEFAULT_RECONCILE_WINDOW_HOURS = 24
DEFAULT_RECONCILE_OVERLAP_MINUTES = 15
PLATFORM_MAP = {
    "PC": "pc",
    "PS4/5": "ps4",
    "XBox": "xboxone",
}


@dataclass(frozen=True)
class AliasRow:
    alias_id: int
    platform: str
    persona_id: int
    player_name: str
    first_seen: datetime
    last_seen: datetime


def bf4sw_database_url() -> str:
    value = os.environ.get("BF4PS_BF4SW_DATABASE_URL")
    if not value:
        raise RuntimeError("BF4PS_BF4SW_DATABASE_URL is required")
    return value


def _alias_from_mapping(row) -> AliasRow:
    return AliasRow(
        alias_id=row["id"],
        platform=row["platform"],
        persona_id=row["persona_id"],
        player_name=row["player_name"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
    )


def load_aliases(source: Connection, *, persona_id: int, platform: str) -> list[AliasRow]:
    rows = source.execute(
        text(
            """
            SELECT id, platform, persona_id, player_name, first_seen, last_seen
            FROM bf4_player_aliases
            WHERE persona_id = :persona_id
              AND platform = :platform
            ORDER BY first_seen, id
            """
        ),
        {"persona_id": persona_id, "platform": platform},
    ).mappings().all()
    if not rows:
        raise LookupError(f"BF4SW aliases not found for platform={platform!r}, persona_id={persona_id}")
    return [_alias_from_mapping(row) for row in rows]


def load_discovery_batch(source: Connection, *, after_alias_id: int, batch_size: int) -> list[AliasRow]:
    rows = source.execute(
        text(
            """
            SELECT id, platform, persona_id, player_name, first_seen, last_seen
            FROM bf4_player_aliases
            WHERE id > :after_alias_id
            ORDER BY id
            LIMIT :batch_size
            """
        ),
        {"after_alias_id": after_alias_id, "batch_size": batch_size},
    ).mappings().all()
    return [_alias_from_mapping(row) for row in rows]


def load_reconciliation_rows(
    source: Connection,
    *,
    since: datetime,
    through: datetime,
) -> list[AliasRow]:
    rows = source.execute(
        text(
            """
            SELECT id, platform, persona_id, player_name, first_seen, last_seen
            FROM bf4_player_aliases
            WHERE persona_id IS NOT NULL
              AND last_seen >= :since
              AND last_seen <= :through
            ORDER BY last_seen, id
            """
        ),
        {"since": since, "through": through},
    ).mappings().all()
    return [_alias_from_mapping(row) for row in rows]


def import_aliases(destination: Connection, aliases: list[AliasRow]) -> int:
    if not aliases:
        raise ValueError("At least one BF4SW alias is required")

    identity = {(alias.platform, alias.persona_id) for alias in aliases}
    if len(identity) != 1:
        raise ValueError("All aliases must belong to the same platform/persona identity")

    source_platform, persona_id = next(iter(identity))
    platform = PLATFORM_MAP.get(source_platform)
    if platform is None:
        raise ValueError(f"Unsupported BF4SW platform {source_platform!r}")

    earliest_seen = min(alias.first_seen for alias in aliases)
    latest_seen = max(alias.last_seen for alias in aliases)
    current_alias = max(aliases, key=lambda alias: (alias.last_seen, alias.alias_id))

    soldier_id = destination.execute(
        text(
            """
            INSERT INTO soldiers (
                persona_id, platform, current_name, first_seen_at, last_seen_at
            )
            VALUES (
                :persona_id, :platform, :name, :first_seen, :last_seen
            )
            ON CONFLICT (persona_id, platform) DO UPDATE SET
                current_name = CASE
                    WHEN EXCLUDED.last_seen_at >= soldiers.last_seen_at
                    THEN EXCLUDED.current_name
                    ELSE soldiers.current_name
                END,
                first_seen_at = LEAST(soldiers.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at = GREATEST(soldiers.last_seen_at, EXCLUDED.last_seen_at),
                updated_at = now()
            RETURNING soldier_id
            """
        ),
        {
            "persona_id": persona_id,
            "platform": platform,
            "name": current_alias.player_name,
            "first_seen": earliest_seen,
            "last_seen": latest_seen,
        },
    ).scalar_one()

    for alias in aliases:
        destination.execute(
            text(
                """
                INSERT INTO soldier_names (soldier_id, name, first_seen_at, last_seen_at)
                VALUES (:soldier_id, :name, :first_seen, :last_seen)
                ON CONFLICT (soldier_id, name) DO UPDATE SET
                    first_seen_at = LEAST(soldier_names.first_seen_at, EXCLUDED.first_seen_at),
                    last_seen_at = GREATEST(soldier_names.last_seen_at, EXCLUDED.last_seen_at)
                """
            ),
            {
                "soldier_id": soldier_id,
                "name": alias.player_name,
                "first_seen": alias.first_seen,
                "last_seen": alias.last_seen,
            },
        )

    destination.execute(
        text(
            """
            INSERT INTO soldier_sources (soldier_id, source_type, first_seen_at, last_seen_at)
            VALUES (:soldier_id, 'bf4sw', :first_seen, :last_seen)
            ON CONFLICT (soldier_id, source_type) DO UPDATE SET
                first_seen_at = LEAST(soldier_sources.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at = GREATEST(soldier_sources.last_seen_at, EXCLUDED.last_seen_at)
            """
        ),
        {
            "soldier_id": soldier_id,
            "first_seen": earliest_seen,
            "last_seen": latest_seen,
        },
    )

    destination.execute(
        text(
            """
            INSERT INTO collection_state (soldier_id)
            VALUES (:soldier_id)
            ON CONFLICT (soldier_id) DO NOTHING
            """
        ),
        {"soldier_id": soldier_id},
    )

    return soldier_id


def ensure_discovery_state(destination: Connection) -> int:
    destination.execute(
        text(
            """
            INSERT INTO discovery_state (source_name, last_alias_id)
            VALUES (:source_name, 0)
            ON CONFLICT (source_name) DO NOTHING
            """
        ),
        {"source_name": SOURCE_NAME},
    )
    return destination.execute(
        text("SELECT last_alias_id FROM discovery_state WHERE source_name = :source_name"),
        {"source_name": SOURCE_NAME},
    ).scalar_one()


def ensure_reconciliation_state(destination: Connection) -> datetime | None:
    destination.execute(
        text(
            """
            INSERT INTO discovery_state (source_name, last_alias_id)
            VALUES (:source_name, 0)
            ON CONFLICT (source_name) DO NOTHING
            """
        ),
        {"source_name": RECONCILE_SOURCE_NAME},
    )
    return destination.execute(
        text("SELECT last_success_at FROM discovery_state WHERE source_name = :source_name"),
        {"source_name": RECONCILE_SOURCE_NAME},
    ).scalar_one()


def run_discovery_batch(source: Connection, destination: Connection, *, batch_size: int) -> tuple[int, int, int, int]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    last_alias_id = ensure_discovery_state(destination)
    destination.execute(
        text(
            """
            UPDATE discovery_state
            SET last_poll_at = now(), updated_at = now()
            WHERE source_name = :source_name
            """
        ),
        {"source_name": SOURCE_NAME},
    )

    batch = load_discovery_batch(source, after_alias_id=last_alias_id, batch_size=batch_size)
    if not batch:
        destination.execute(
            text(
                """
                UPDATE discovery_state
                SET last_success_at = now(), last_error = NULL, updated_at = now()
                WHERE source_name = :source_name
                """
            ),
            {"source_name": SOURCE_NAME},
        )
        return last_alias_id, last_alias_id, 0, 0

    identities = sorted({(alias.platform, alias.persona_id) for alias in batch})
    for platform, persona_id in identities:
        aliases = load_aliases(source, persona_id=persona_id, platform=platform)
        import_aliases(destination, aliases)

    new_last_alias_id = batch[-1].alias_id
    destination.execute(
        text(
            """
            UPDATE discovery_state
            SET last_alias_id = :last_alias_id,
                last_success_at = now(),
                last_error = NULL,
                updated_at = now()
            WHERE source_name = :source_name
            """
        ),
        {"source_name": SOURCE_NAME, "last_alias_id": new_last_alias_id},
    )
    return last_alias_id, new_last_alias_id, len(batch), len(identities)


def run_reconciliation(
    source: Connection,
    destination: Connection,
    *,
    initial_window_hours: int = DEFAULT_RECONCILE_WINDOW_HOURS,
    overlap_minutes: int = DEFAULT_RECONCILE_OVERLAP_MINUTES,
) -> tuple[datetime, datetime, int, int]:
    if initial_window_hours < 1:
        raise ValueError("initial_window_hours must be at least 1")
    if overlap_minutes < 0:
        raise ValueError("overlap_minutes cannot be negative")

    previous_success = ensure_reconciliation_state(destination)
    source_now = source.execute(text("SELECT clock_timestamp()")) .scalar_one()

    if previous_success is None:
        since = source_now - timedelta(hours=initial_window_hours)
    else:
        since = previous_success - timedelta(minutes=overlap_minutes)

    destination.execute(
        text(
            """
            UPDATE discovery_state
            SET last_poll_at = now(), updated_at = now()
            WHERE source_name = :source_name
            """
        ),
        {"source_name": RECONCILE_SOURCE_NAME},
    )

    rows = load_reconciliation_rows(source, since=since, through=source_now)
    grouped: dict[tuple[str, int], list[AliasRow]] = {}
    for alias in rows:
        grouped.setdefault((alias.platform, alias.persona_id), []).append(alias)

    for aliases in grouped.values():
        import_aliases(destination, aliases)

    # Store the source database's timestamp as the watermark. This deliberately
    # avoids depending on the application host and source DB sharing a display
    # timezone or perfectly identical wall-clock configuration.
    destination.execute(
        text(
            """
            UPDATE discovery_state
            SET last_success_at = :source_watermark,
                last_error = NULL,
                updated_at = now()
            WHERE source_name = :source_name
            """
        ),
        {
            "source_name": RECONCILE_SOURCE_NAME,
            "source_watermark": source_now,
        },
    )

    return since, source_now, len(rows), len(grouped)


def run_catch_up(source_engine, destination_engine, *, batch_size: int) -> None:
    batch_number = 0
    total_alias_rows = 0
    total_identities = 0

    while True:
        with source_engine.connect() as source:
            with destination_engine.begin() as destination:
                old_cursor, new_cursor, alias_rows, identities = run_discovery_batch(
                    source, destination, batch_size=batch_size
                )

        if alias_rows == 0:
            print(
                f"BF4SW discovery caught up at cursor={new_cursor}: "
                f"batches={batch_number} alias_rows={total_alias_rows} "
                f"identity_visits={total_identities}"
            )
            return

        batch_number += 1
        total_alias_rows += alias_rows
        total_identities += identities
        print(
            f"Batch {batch_number}: cursor={old_cursor}->{new_cursor} "
            f"alias_rows={alias_rows} identities={identities}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import BF4SW soldiers into BF4PS.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--persona-id", type=int, help="Import one known BF4SW persona and complete alias history.")
    mode.add_argument("--discover", action="store_true", help="Run one bounded BF4SW discovery batch.")
    mode.add_argument("--discover-until-caught-up", action="store_true", help="Run bounded discovery batches until BF4SW has no rows beyond the cursor.")
    mode.add_argument("--reconcile", action="store_true", help="Refresh mutable BF4SW alias observations using a source-time watermark.")
    parser.add_argument("--platform", choices=sorted(PLATFORM_MAP), help="BF4SW platform; required with --persona-id.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"Alias rows per discovery batch (default: {DEFAULT_BATCH_SIZE}).")
    parser.add_argument("--reconcile-window-hours", type=int, default=DEFAULT_RECONCILE_WINDOW_HOURS, help=f"Initial reconciliation activity window in hours (default: {DEFAULT_RECONCILE_WINDOW_HOURS}).")
    parser.add_argument("--reconcile-overlap-minutes", type=int, default=DEFAULT_RECONCILE_OVERLAP_MINUTES, help=f"Reconciliation watermark overlap in minutes (default: {DEFAULT_RECONCILE_OVERLAP_MINUTES}).")
    args = parser.parse_args()

    source_engine = create_engine(bf4sw_database_url())
    destination_engine = create_engine(database_url())

    if args.persona_id is not None:
        if args.platform is None:
            parser.error("--platform is required with --persona-id")
        with source_engine.connect() as source:
            aliases = load_aliases(source, persona_id=args.persona_id, platform=args.platform)
        with destination_engine.begin() as destination:
            soldier_id = import_aliases(destination, aliases)
        current_alias = max(aliases, key=lambda alias: (alias.last_seen, alias.alias_id))
        print(
            f"Imported BF4SW persona_id={current_alias.persona_id} platform={current_alias.platform} "
            f"aliases={len(aliases)} current_name={current_alias.player_name!r} "
            f"as BF4PS soldier_id={soldier_id}"
        )
        return

    if args.platform is not None:
        parser.error("--platform is only valid with --persona-id")

    if args.discover_until_caught_up:
        run_catch_up(source_engine, destination_engine, batch_size=args.batch_size)
        return

    if args.reconcile:
        with source_engine.connect() as source:
            with destination_engine.begin() as destination:
                since, through, alias_rows, identities = run_reconciliation(
                    source,
                    destination,
                    initial_window_hours=args.reconcile_window_hours,
                    overlap_minutes=args.reconcile_overlap_minutes,
                )
        print(
            f"BF4SW reconciliation complete: since={since.isoformat()} "
            f"through={through.isoformat()} alias_rows={alias_rows} "
            f"identities={identities}"
        )
        return

    with source_engine.connect() as source:
        with destination_engine.begin() as destination:
            old_cursor, new_cursor, alias_rows, identities = run_discovery_batch(
                source, destination, batch_size=args.batch_size
            )

    print(
        f"BF4SW discovery batch complete: cursor={old_cursor}->{new_cursor} "
        f"alias_rows={alias_rows} identities={identities}"
    )


if __name__ == "__main__":
    main()

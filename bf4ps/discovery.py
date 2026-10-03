from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from bf4ps.config import database_url

SOURCE_NAME = "bf4sw"
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


def load_alias(source: Connection, *, persona_id: int, platform: str) -> AliasRow:
    row = source.execute(
        text(
            """
            SELECT id, platform, persona_id, player_name, first_seen, last_seen
            FROM bf4_player_aliases
            WHERE persona_id = :persona_id
              AND platform = :platform
            ORDER BY last_seen DESC, id DESC
            LIMIT 1
            """
        ),
        {"persona_id": persona_id, "platform": platform},
    ).mappings().one_or_none()
    if row is None:
        raise LookupError(f"BF4SW alias not found for platform={platform!r}, persona_id={persona_id}")
    return AliasRow(
        alias_id=row["id"],
        platform=row["platform"],
        persona_id=row["persona_id"],
        player_name=row["player_name"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
    )


def import_alias(destination: Connection, alias: AliasRow) -> int:
    platform = PLATFORM_MAP.get(alias.platform)
    if platform is None:
        raise ValueError(f"Unsupported BF4SW platform {alias.platform!r}")

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
                current_name = EXCLUDED.current_name,
                first_seen_at = LEAST(soldiers.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at = GREATEST(soldiers.last_seen_at, EXCLUDED.last_seen_at),
                updated_at = now()
            RETURNING soldier_id
            """
        ),
        {
            "persona_id": alias.persona_id,
            "platform": platform,
            "name": alias.player_name,
            "first_seen": alias.first_seen,
            "last_seen": alias.last_seen,
        },
    ).scalar_one()

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
            "first_seen": alias.first_seen,
            "last_seen": alias.last_seen,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Import one known BF4SW alias into BF4PS.")
    parser.add_argument("--persona-id", type=int, required=True)
    parser.add_argument("--platform", choices=sorted(PLATFORM_MAP), required=True)
    args = parser.parse_args()

    source_engine = create_engine(bf4sw_database_url())
    destination_engine = create_engine(database_url())

    with source_engine.connect() as source:
        alias = load_alias(source, persona_id=args.persona_id, platform=args.platform)

    with destination_engine.begin() as destination:
        soldier_id = import_alias(destination, alias)

    print(
        f"Imported BF4SW alias id={alias.alias_id} "
        f"persona_id={alias.persona_id} platform={alias.platform} "
        f"name={alias.player_name!r} as BF4PS soldier_id={soldier_id}"
    )


if __name__ == "__main__":
    main()

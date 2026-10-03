"""Initial BF4 Player Stats schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

PLATFORMS = ("pc", "ps4", "xboxone")
RESOURCES = ("detailed", "profile", "weapons", "vehicles")
COLLECTION_RESULTS = ("never_attempted", "success", "temporary_failure", "unavailable")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _detailed_columns() -> list[sa.Column]:
    # Raw values retained by Detailed Stats Retention Contract v1.
    return [
        sa.Column("rank", sa.BigInteger(), nullable=True),
        sa.Column("time_played_seconds", sa.BigInteger(), nullable=True),
        sa.Column("assault_score", sa.BigInteger(), nullable=True),
        sa.Column("engineer_score", sa.BigInteger(), nullable=True),
        sa.Column("support_score", sa.BigInteger(), nullable=True),
        sa.Column("recon_score", sa.BigInteger(), nullable=True),
        sa.Column("commander_score", sa.BigInteger(), nullable=True),
        sa.Column("squad_score", sa.BigInteger(), nullable=True),
        sa.Column("vehicle_score", sa.BigInteger(), nullable=True),
        sa.Column("award_score", sa.BigInteger(), nullable=True),
        sa.Column("unlock_score", sa.BigInteger(), nullable=True),
        sa.Column("total_score", sa.BigInteger(), nullable=True),
        sa.Column("combat_score", sa.BigInteger(), nullable=True),
        sa.Column("conquest_score", sa.BigInteger(), nullable=True),
        sa.Column("rush_score", sa.BigInteger(), nullable=True),
        sa.Column("team_deathmatch_score", sa.BigInteger(), nullable=True),
        sa.Column("domination_score", sa.BigInteger(), nullable=True),
        sa.Column("obliteration_score", sa.BigInteger(), nullable=True),
        sa.Column("defuse_score", sa.BigInteger(), nullable=True),
        sa.Column("capture_the_flag_score", sa.BigInteger(), nullable=True),
        sa.Column("air_superiority_score", sa.BigInteger(), nullable=True),
        sa.Column("carrier_assault_score", sa.BigInteger(), nullable=True),
        sa.Column("chain_link_score", sa.BigInteger(), nullable=True),
        sa.Column("gun_master_score", sa.BigInteger(), nullable=True),
        sa.Column("kills", sa.BigInteger(), nullable=True),
        sa.Column("deaths", sa.BigInteger(), nullable=True),
        sa.Column("kill_assists", sa.BigInteger(), nullable=True),
        sa.Column("wins", sa.BigInteger(), nullable=True),
        sa.Column("losses", sa.BigInteger(), nullable=True),
        sa.Column("shots_fired", sa.BigInteger(), nullable=True),
        sa.Column("shots_hit", sa.BigInteger(), nullable=True),
        sa.Column("repairs", sa.BigInteger(), nullable=True),
        sa.Column("revives", sa.BigInteger(), nullable=True),
        sa.Column("heals", sa.BigInteger(), nullable=True),
        sa.Column("resupplies", sa.BigInteger(), nullable=True),
        sa.Column("avenger_kills", sa.BigInteger(), nullable=True),
        sa.Column("savior_kills", sa.BigInteger(), nullable=True),
        sa.Column("suppression_assists", sa.BigInteger(), nullable=True),
        sa.Column("quit_percentage", sa.Numeric(10, 6), nullable=True),
        sa.Column("flags_captured", sa.BigInteger(), nullable=True),
        sa.Column("flags_defended", sa.BigInteger(), nullable=True),
        sa.Column("dogtags_taken", sa.BigInteger(), nullable=True),
        sa.Column("vehicles_destroyed", sa.BigInteger(), nullable=True),
        sa.Column("vehicle_damage", sa.BigInteger(), nullable=True),
        sa.Column("headshots", sa.BigInteger(), nullable=True),
        sa.Column("longest_headshot", sa.Numeric(14, 4), nullable=True),
        sa.Column("highest_kill_streak", sa.BigInteger(), nullable=True),
        sa.Column("nemesis_kills", sa.BigInteger(), nullable=True),
        sa.Column("highest_nemesis_streak", sa.BigInteger(), nullable=True),
    ]


def _state_columns(prefix: str) -> list[sa.Column]:
    return [
        sa.Column(f"{prefix}_state", sa.Text(), nullable=False, server_default="never_attempted"),
        sa.Column(f"{prefix}_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(f"{prefix}_last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(f"{prefix}_next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(f"{prefix}_consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(f"{prefix}_last_error_class", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_last_error_message", sa.Text(), nullable=True),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "soldiers",
        sa.Column("soldier_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("current_name", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("persona_id", "platform", name="uq_soldiers_persona_platform"),
        sa.CheckConstraint("platform IN ('pc','ps4','xboxone')", name="soldiers_platform_check"),
        sa.CheckConstraint("btrim(current_name) <> ''", name="soldiers_name_nonempty"),
    )
    op.create_index("ix_soldiers_current_name_lower", "soldiers", [sa.text("lower(current_name)")])
    op.create_index("ix_soldiers_last_seen", "soldiers", ["last_seen_at"])

    op.create_table(
        "soldier_sources",
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_type", sa.Text(), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_type IN ('bf4sw','manual')", name="soldier_sources_type_check"),
    )

    op.create_table(
        "soldier_names",
        sa.Column("soldier_name_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("soldier_id", "name", name="uq_soldier_names_soldier_name"),
        sa.CheckConstraint("btrim(name) <> ''", name="soldier_names_name_nonempty"),
    )
    op.create_index("ix_soldier_names_name_lower", "soldier_names", [sa.text("lower(name)")])

    op.create_table(
        "battlelog_profiles",
        sa.Column("profile_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("battlelog_username", sa.Text(), nullable=False),
        sa.Column("battlelog_user_id", sa.BigInteger(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("country_name", sa.Text(), nullable=True),
        sa.Column("access_state", sa.Text(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("access_state IN ('public_country','public_no_country','friends_only','not_found','error')", name="battlelog_profiles_access_state_check"),
        sa.CheckConstraint("country_code IS NULL OR country_code = upper(country_code)", name="battlelog_profiles_country_upper_check"),
    )
    op.create_index("uq_battlelog_profiles_username_lower", "battlelog_profiles", [sa.text("lower(battlelog_username)")], unique=True)

    op.create_table(
        "profile_soldiers",
        sa.Column("profile_id", sa.BigInteger(), sa.ForeignKey("battlelog_profiles.profile_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "detailed_stats_current",
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), primary_key=True),
        *_detailed_columns(),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "detailed_stats_history",
        sa.Column("snapshot_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), nullable=False),
        *_detailed_columns(),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_detailed_history_soldier_observed", "detailed_stats_history", ["soldier_id", sa.text("observed_at DESC")])

    op.create_table(
        "weapon_catalog",
        sa.Column("weapon_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("weapon_guid", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "soldier_weapon_stats",
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("weapon_id", sa.BigInteger(), sa.ForeignKey("weapon_catalog.weapon_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kills", sa.BigInteger(), nullable=False),
        sa.Column("headshots", sa.BigInteger(), nullable=False),
        sa.Column("shots_fired", sa.BigInteger(), nullable=False),
        sa.Column("shots_hit", sa.BigInteger(), nullable=False),
        sa.Column("time_equipped_seconds", sa.BigInteger(), nullable=False),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "vehicle_catalog",
        sa.Column("vehicle_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("vehicle_guid", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "soldier_vehicle_stats",
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("vehicle_id", sa.BigInteger(), sa.ForeignKey("vehicle_catalog.vehicle_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kills", sa.BigInteger(), nullable=False),
        sa.Column("time_in_seconds", sa.BigInteger(), nullable=False),
        sa.Column("destroy_x_in_y", sa.BigInteger(), nullable=True),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    state_columns: list[sa.Column] = []
    for resource in RESOURCES:
        state_columns.extend(_state_columns(resource))
    state_checks = [
        sa.CheckConstraint(f"{resource}_state IN ('never_attempted','success','temporary_failure','unavailable')", name=f"collection_state_{resource}_state_check")
        for resource in RESOURCES
    ]
    failure_checks = [
        sa.CheckConstraint(f"{resource}_consecutive_failures >= 0", name=f"collection_state_{resource}_failures_check")
        for resource in RESOURCES
    ]
    op.create_table(
        "collection_state",
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), primary_key=True),
        *state_columns,
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        *state_checks,
        *failure_checks,
    )
    for resource in RESOURCES:
        op.create_index(f"ix_collection_state_{resource}_due", "collection_state", [f"{resource}_next_due_at"], postgresql_where=sa.text(f"{resource}_next_due_at IS NOT NULL"))

    op.create_table(
        "discovery_state",
        sa.Column("source_name", sa.Text(), primary_key=True),
        sa.Column("last_alias_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("last_alias_id >= 0", name="discovery_state_alias_id_check"),
    )

    op.create_table(
        "collectors",
        sa.Column("collector_uuid", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("collector_name", sa.Text(), nullable=False),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("lane", sa.Text(), nullable=False),
        sa.Column("egress_key", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("drained", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("software_version", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_state", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("heartbeat_lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_job_id", sa.BigInteger(), nullable=True),
        *_timestamps(),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("btrim(collector_name) <> ''", name="collectors_name_nonempty"),
        sa.CheckConstraint("btrim(hostname) <> ''", name="collectors_hostname_nonempty"),
        sa.CheckConstraint("btrim(egress_key) <> ''", name="collectors_egress_nonempty"),
        sa.CheckConstraint("lane IN ('background','interactive')", name="collectors_lane_check"),
        sa.CheckConstraint("heartbeat_state IN ('unknown','healthy','lost')", name="collectors_heartbeat_state_check"),
    )
    op.create_index("uq_collectors_active_name", "collectors", [sa.text("lower(collector_name)")], unique=True, postgresql_where=sa.text("retired_at IS NULL"))
    op.create_index("ix_collectors_heartbeat", "collectors", ["heartbeat_state", "last_heartbeat_at"], postgresql_where=sa.text("retired_at IS NULL"))
    op.create_index("ix_collectors_egress", "collectors", ["egress_key"], postgresql_where=sa.text("retired_at IS NULL"))

    op.create_table(
        "collection_jobs",
        sa.Column("job_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("lane", sa.Text(), nullable=False),
        sa.Column("priority_class", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("priority_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("collector_uuid", postgresql.UUID(as_uuid=True), sa.ForeignKey("collectors.collector_uuid", ondelete="SET NULL"), nullable=True),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_class", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("soldier_id", "resource", name="uq_collection_jobs_soldier_resource"),
        sa.CheckConstraint("resource IN ('detailed','profile','weapons','vehicles')", name="collection_jobs_resource_check"),
        sa.CheckConstraint("lane IN ('background','interactive')", name="collection_jobs_lane_check"),
        sa.CheckConstraint("priority_class IN ('interactive','active','recent','bootstrap')", name="collection_jobs_priority_class_check"),
        sa.CheckConstraint("status IN ('pending','claimed','running')", name="collection_jobs_status_check"),
        sa.CheckConstraint("attempt_count >= 0", name="collection_jobs_attempt_count_check"),
        sa.CheckConstraint("((status = 'pending' AND collector_uuid IS NULL AND lease_token IS NULL AND claimed_at IS NULL AND started_at IS NULL AND lease_expires_at IS NULL) OR (status = 'claimed' AND collector_uuid IS NOT NULL AND lease_token IS NOT NULL AND claimed_at IS NOT NULL AND started_at IS NULL AND lease_expires_at IS NOT NULL) OR (status = 'running' AND collector_uuid IS NOT NULL AND lease_token IS NOT NULL AND claimed_at IS NOT NULL AND started_at IS NOT NULL AND lease_expires_at IS NOT NULL))", name="collection_jobs_lease_shape_check"),
    )
    op.create_index("ix_collection_jobs_claim", "collection_jobs", ["lane", "priority_class", sa.text("priority_value DESC"), "eligible_at", "created_at", "job_id"], postgresql_where=sa.text("status = 'pending'"))
    op.create_index("ix_collection_jobs_expired_lease", "collection_jobs", ["lease_expires_at", "job_id"], postgresql_where=sa.text("status IN ('claimed','running')"))
    op.create_index("ix_collection_jobs_collector", "collection_jobs", ["collector_uuid"], postgresql_where=sa.text("collector_uuid IS NOT NULL"))
    op.create_foreign_key("fk_collectors_current_job", "collectors", "collection_jobs", ["current_job_id"], ["job_id"], ondelete="SET NULL")

    op.create_table(
        "collection_events",
        sa.Column("event_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("collector_uuid", postgresql.UUID(as_uuid=True), sa.ForeignKey("collectors.collector_uuid", ondelete="SET NULL"), nullable=True),
        sa.Column("collector_name_snapshot", sa.Text(), nullable=True),
        sa.Column("hostname_snapshot", sa.Text(), nullable=True),
        sa.Column("egress_key_snapshot", sa.Text(), nullable=True),
        sa.Column("job_id", sa.BigInteger(), nullable=True),
        sa.Column("soldier_id", sa.BigInteger(), sa.ForeignKey("soldiers.soldier_id", ondelete="SET NULL"), nullable=True),
        sa.Column("persona_id", sa.BigInteger(), nullable=True),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("lane", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_class", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("resource IS NULL OR resource IN ('detailed','profile','weapons','vehicles')", name="collection_events_resource_check"),
        sa.CheckConstraint("lane IS NULL OR lane IN ('background','interactive')", name="collection_events_lane_check"),
        sa.CheckConstraint("platform IS NULL OR platform IN ('pc','ps4','xboxone')", name="collection_events_platform_check"),
        sa.CheckConstraint("attempt_number IS NULL OR attempt_number >= 0", name="collection_events_attempt_check"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="collection_events_duration_check"),
        sa.CheckConstraint("http_status IS NULL OR http_status BETWEEN 100 AND 599", name="collection_events_http_status_check"),
        sa.CheckConstraint("btrim(event_type) <> ''", name="collection_events_event_type_nonempty"),
    )
    op.create_index("ix_collection_events_time", "collection_events", [sa.text("occurred_at DESC")])
    op.create_index("ix_collection_events_collector_time", "collection_events", ["collector_uuid", sa.text("occurred_at DESC")])
    op.create_index("ix_collection_events_soldier_time", "collection_events", ["soldier_id", sa.text("occurred_at DESC")], postgresql_where=sa.text("soldier_id IS NOT NULL"))
    op.create_index("ix_collection_events_persona_time", "collection_events", ["platform", "persona_id", sa.text("occurred_at DESC")], postgresql_where=sa.text("persona_id IS NOT NULL"))
    op.create_index("ix_collection_events_job", "collection_events", ["job_id", "occurred_at"], postgresql_where=sa.text("job_id IS NOT NULL"))
    op.create_index("ix_collection_events_type_time", "collection_events", ["event_type", sa.text("occurred_at DESC")])
    op.create_index("ix_collection_events_http_errors", "collection_events", ["http_status", sa.text("occurred_at DESC")], postgresql_where=sa.text("http_status IS NOT NULL"))


def downgrade() -> None:
    op.drop_table("collection_events")
    op.drop_constraint("fk_collectors_current_job", "collectors", type_="foreignkey")
    op.drop_table("collection_jobs")
    op.drop_table("collectors")
    op.drop_table("discovery_state")
    op.drop_table("collection_state")
    op.drop_table("soldier_vehicle_stats")
    op.drop_table("vehicle_catalog")
    op.drop_table("soldier_weapon_stats")
    op.drop_table("weapon_catalog")
    op.drop_table("detailed_stats_history")
    op.drop_table("detailed_stats_current")
    op.drop_table("profile_soldiers")
    op.drop_table("battlelog_profiles")
    op.drop_table("soldier_names")
    op.drop_table("soldier_sources")
    op.drop_table("soldiers")

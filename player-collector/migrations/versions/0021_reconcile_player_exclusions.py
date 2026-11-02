"""Reconcile pre-existing production exclusion guard with Alembic history.

Revision ID: 0021_reconcile_player_exclusions
Revises: 0020_compact_rank_snapshots

Production already has this table/trigger, created outside migrations. Never
replace or mutate those objects if present: validate their signatures instead.
"""
from alembic import op
import sqlalchemy as sa

revision = '0021_reconcile_player_exclusions'
down_revision = '0020_compact_rank_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing = conn.execute(sa.text("SELECT to_regclass('public.player_exclusions')")).scalar()
    if existing is None:
        op.create_table('player_exclusions',
            sa.Column('platform', sa.Text, primary_key=True),
            sa.Column('persona_id', sa.BigInteger, primary_key=True),
            sa.Column('reason_code', sa.Text, nullable=False),
            sa.Column('private_note', sa.Text),
            sa.Column('created_by', sa.Text, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('active', sa.Boolean, nullable=False, server_default=sa.true()),
            sa.CheckConstraint("platform IN ('pc','ps4','xboxone')", name='player_exclusions_platform_check'),
            sa.CheckConstraint('persona_id > 0', name='player_exclusions_persona_id_check'))
        op.create_index('ix_player_exclusions_active', 'player_exclusions', ['platform','persona_id'],
                        postgresql_where=sa.text('active'))
    # Validate even on scratch; never silently accept incompatible production DDL.
    expected = [('platform','text','NO'),('persona_id','bigint','NO'),
                ('reason_code','text','NO'),('private_note','text','YES'),
                ('created_by','text','NO'),('created_at','timestamp with time zone','NO'),
                ('updated_at','timestamp with time zone','NO'),('active','boolean','NO')]
    actual = conn.execute(sa.text("""SELECT column_name,data_type,is_nullable
        FROM information_schema.columns WHERE table_schema='public'
        AND table_name='player_exclusions' ORDER BY ordinal_position""")).all()
    if [tuple(row) for row in actual] != expected:
        raise RuntimeError('player_exclusions schema differs from verified production shape')
    # Restore production's security-definer guard on fresh installations only.
    guard = conn.execute(sa.text("SELECT to_regprocedure('public.bf4ps_reject_excluded_soldier()')")).scalar()
    if guard is None:
        op.execute("""CREATE FUNCTION public.bf4ps_reject_excluded_soldier() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path TO pg_catalog, pg_temp AS $$
          BEGIN IF EXISTS (SELECT 1 FROM public.player_exclusions e
            WHERE e.platform=NEW.platform AND e.persona_id=NEW.persona_id AND e.active)
            THEN RAISE EXCEPTION 'excluded soldier identity' USING ERRCODE='23514';
          END IF; RETURN NEW; END $$""")
    trigger = conn.execute(sa.text("""SELECT 1 FROM pg_trigger WHERE tgrelid='public.soldiers'::regclass
       AND tgname='bf4ps_exclusion_soldiers' AND NOT tgisinternal""")).scalar()
    if trigger is None:
        op.execute("""CREATE TRIGGER bf4ps_exclusion_soldiers BEFORE INSERT OR UPDATE OF
          persona_id,platform ON public.soldiers FOR EACH ROW
          EXECUTE FUNCTION public.bf4ps_reject_excluded_soldier()""")


def downgrade():
    # Objects predate Alembic in production: never remove moderation protections.
    pass

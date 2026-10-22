"""Initial complete Discord control plane schema.

Revision ID: 0001_discord_initial
Revises:
"""
from pathlib import Path
from alembic import op
revision='0001_discord_initial'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
 sql=(Path(__file__).resolve().parents[2]/'schema'/'0001_initial.sql').read_text()
 # Baseline SQL also bootstraps alembic_version; Alembic itself owns that table.
 sql=sql.replace('BEGIN;','',1).rsplit('COMMIT;',1)[0]
 sql=sql.replace('CREATE TABLE alembic_version(version_num varchar(32) NOT NULL PRIMARY KEY);','')
 sql=sql.replace("INSERT INTO alembic_version VALUES ('0001_discord_initial');",'')
 for statement in sql.split(";"):
  if statement.strip(): op.execute(statement.strip())

def downgrade():
 raise RuntimeError('Baseline downgrade is intentionally unsupported; never drop the bot control plane automatically')

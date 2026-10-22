import os
from alembic import context
from sqlalchemy import engine_from_config, pool
config=context.config
url=os.environ.get('BOT_DATABASE_URL')
if url:
 url=url.replace('postgresql://','postgresql+psycopg://',1)
 config.set_main_option('sqlalchemy.url',url.replace('%','%%'))
if context.is_offline_mode():
 context.configure(url=config.get_main_option('sqlalchemy.url'),literal_binds=True)
 with context.begin_transaction(): context.run_migrations()
else:
 engine=engine_from_config(config.get_section(config.config_ini_section),prefix='sqlalchemy.',poolclass=pool.NullPool)
 with engine.connect() as connection:
  context.configure(connection=connection)
  with context.begin_transaction(): context.run_migrations()

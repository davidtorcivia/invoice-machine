"""Alembic migration environment configuration."""

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from invoice_machine.config import get_settings
from invoice_machine.database import Base

config = context.config

# Only take over logging when nothing has configured it yet (the alembic CLI).
# In-process upgrades run after main.py's basicConfig; fileConfig would reset
# the root logger to WARN and silence every application logger.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

settings = get_settings()
db_url = settings.database_url
# Use synchronous sqlite driver for migrations (not aiosqlite)
if "aiosqlite" in db_url:
    db_url = db_url.replace("sqlite+aiosqlite", "sqlite", 1)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode, emitting SQL instead of executing it."""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with sync engine."""
    from invoice_machine.database import register_sqlite_pragmas

    connectable = create_engine(
        db_url,
        poolclass=pool.NullPool,
    )
    # Enforce foreign keys (so DDL respecting FKs behaves) and avoid lock errors.
    register_sqlite_pragmas(connectable)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

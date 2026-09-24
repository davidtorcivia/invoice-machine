"""Alembic migration environment configuration."""

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event, pool

from invoice_machine.config import get_settings
from invoice_machine.database import Base

config = context.config
logger = logging.getLogger("alembic.env")

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


def _fk_violations(connection) -> set[tuple]:
    # (table, rowid, parent) without fkid: a table rebuild can renumber its keys.
    return {tuple(row[:3]) for row in connection.exec_driver_sql("PRAGMA foreign_key_check")}


def run_migrations_online() -> None:
    """Run the whole upgrade in one transaction with foreign keys off."""
    from invoice_machine.database import apply_sqlite_pragmas

    connectable = create_engine(db_url, poolclass=pool.NullPool)

    @event.listens_for(connectable, "connect")
    def _connect(dbapi_connection, _connection_record):
        # pysqlite only begins a transaction before DML, leaving DDL outside it;
        # hand BEGIN to SQLAlchemy so a failed upgrade rolls back whole.
        dbapi_connection.isolation_level = None
        # Must be set outside a transaction. A table rebuild drops the old table,
        # and with foreign keys on that drop cascades into child tables.
        apply_sqlite_pragmas(dbapi_connection, foreign_keys=False)

    @event.listens_for(connectable, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    with connectable.connect() as connection:
        # SQLite's alembic impl defaults to one transaction per migration.
        context.configure(
            connection=connection, target_metadata=target_metadata, transactional_ddl=True
        )

        with context.begin_transaction():
            existing = _fk_violations(connection)
            if existing:
                logger.warning(
                    "Database has %d foreign key violations from before this upgrade: %s",
                    len(existing),
                    sorted(existing, key=str)[:20],
                )
            context.run_migrations()
            introduced = _fk_violations(connection) - existing
            if introduced:
                raise RuntimeError(
                    "Migrations introduced foreign key violations, rolled back: "
                    f"{sorted(introduced, key=str)[:20]}"
                )

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

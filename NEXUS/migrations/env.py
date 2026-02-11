"""Alembic environment configuration.

Reads the database URL from app.config.Settings (which in turn reads from
environment variables / .env file) so that the connection string is never
hard-coded.

Uses psycopg2 (sync driver) for Alembic migrations while the application
itself uses asyncpg for async database access.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import Settings

# ---------------------------------------------------------------------------
# Alembic Config object (provides access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Override sqlalchemy.url from application Settings
# ---------------------------------------------------------------------------
settings = Settings()
config.set_main_option("sqlalchemy.url", settings.postgres_url_sync)

# ---------------------------------------------------------------------------
# Target metadata — import your SQLAlchemy Base here once ORM models exist.
# For now we use None (raw SQL migrations only).
# ---------------------------------------------------------------------------
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates a synchronous engine (psycopg2) and runs migrations inside a
    transaction.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

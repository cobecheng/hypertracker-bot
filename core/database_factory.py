"""
Database factory for selecting the active backend.

Today the app still runs on SQLite by default. This module creates a single
selection point so we can migrate entrypoints to Postgres/Supabase later
without changing the rest of the bot in one big bang.
"""
from config import Settings
from core.database import Database
from core.postgres_database import PostgresDatabase


def create_database(settings: Settings):
    """Create the configured database backend."""
    if settings.database_backend == "sqlite":
        return Database(settings.database_path)

    if settings.database_backend == "postgres":
        if not settings.database_url:
            raise ValueError("DATABASE_URL is required when DATABASE_BACKEND=postgres")
        return PostgresDatabase(settings.database_url)

    raise ValueError(f"Unsupported database backend: {settings.database_backend}")

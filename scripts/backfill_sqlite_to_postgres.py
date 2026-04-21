#!/usr/bin/env python3
"""
Backfill HyperTracker data from the local SQLite database into Postgres/Supabase.

Usage:
    DATABASE_URL=postgresql://... python scripts/backfill_sqlite_to_postgres.py

The target Postgres database is expected to already have the schema from
sql/supabase_schema.sql applied.
"""
import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import asyncpg

from config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TABLE_ORDER = [
    "users",
    "wallets",
    "settings",
    "wallet_fill_events",
    "wallet_hourly_summary_state",
    "wallet_live_snapshots",
    "evm_tracked_addresses",
]


def sqlite_conn():
    settings = get_settings()
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_rows(conn: sqlite3.Connection, table_name: str):
    cursor = conn.execute(f"SELECT * FROM {table_name}")
    return [dict(row) for row in cursor.fetchall()]


def normalize_row(table_name: str, row: dict) -> dict:
    row = dict(row)

    if table_name in {"wallets", "settings"}:
        if "filters_json" in row and row["filters_json"] is not None:
            row["filters_json"] = json.loads(row["filters_json"])
        if "liq_filters_json" in row and row["liq_filters_json"] is not None:
            row["liq_filters_json"] = json.loads(row["liq_filters_json"])
        if "global_wallet_filters_json" in row and row["global_wallet_filters_json"] is not None:
            row["global_wallet_filters_json"] = json.loads(row["global_wallet_filters_json"])

    if table_name == "wallet_live_snapshots":
        row["positions_json"] = json.loads(row["positions_json"])
        row["raw_snapshot_json"] = json.loads(row["raw_snapshot_json"])

    for key in ("active", "liq_monitor_enabled", "liquidation", "is_close"):
        if key in row and row[key] is not None:
            row[key] = bool(row[key])

    for key, value in list(row.items()):
        if key.endswith("_at") or key.endswith("_iso"):
            if value is not None and isinstance(value, str):
                row[key] = datetime.fromisoformat(value)

    return row


def encode_row_for_postgres(row: dict) -> dict:
    """Convert Python objects into asyncpg-friendly values."""
    encoded = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            encoded[key] = json.dumps(value)
        else:
            encoded[key] = value
    return encoded


async def truncate_target(conn: asyncpg.Connection):
    await conn.execute(
        """
        truncate table
            public.evm_tracked_addresses,
            public.wallet_live_snapshots,
            public.wallet_hourly_summary_state,
            public.wallet_fill_events,
            public.settings,
            public.wallets,
            public.users
        restart identity cascade
        """
    )


async def insert_rows(conn: asyncpg.Connection, table_name: str, rows: list[dict]):
    if not rows:
        print(f"{table_name}: no rows to insert")
        return

    rows = [encode_row_for_postgres(row) for row in rows]
    columns = list(rows[0].keys())
    column_sql = ", ".join(columns)
    placeholder_sql = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
    query = f"INSERT INTO public.{table_name} ({column_sql}) VALUES ({placeholder_sql})"
    payload = [tuple(row[column] for column in columns) for row in rows]

    await conn.executemany(query, payload)
    print(f"{table_name}: inserted {len(rows)} rows")


async def reset_sequences(conn: asyncpg.Connection):
    await conn.execute(
        """
        select setval(
            pg_get_serial_sequence('public.wallets', 'id'),
            coalesce((select max(id) from public.wallets), 1),
            true
        )
        """
    )
    await conn.execute(
        """
        select setval(
            pg_get_serial_sequence('public.wallet_fill_events', 'id'),
            coalesce((select max(id) from public.wallet_fill_events), 1),
            true
        )
        """
    )
    await conn.execute(
        """
        select setval(
            pg_get_serial_sequence('public.evm_tracked_addresses', 'id'),
            coalesce((select max(id) from public.evm_tracked_addresses), 1),
            true
        )
        """
    )


async def verify_counts(pg_conn: asyncpg.Connection, sqlite_db: sqlite3.Connection):
    for table_name in TABLE_ORDER:
        sqlite_count = sqlite_db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        postgres_count = await pg_conn.fetchval(f"SELECT COUNT(*) FROM public.{table_name}")
        status = "OK" if sqlite_count == postgres_count else "MISMATCH"
        print(f"verify {table_name}: sqlite={sqlite_count} postgres={postgres_count} [{status}]")


async def main():
    settings = get_settings()
    database_url = settings.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required for Postgres/Supabase backfill")

    sqlite_db = sqlite_conn()
    try:
        print(f"SQLite source: {settings.database_path}")
        pg_conn = await asyncpg.connect(database_url)
        try:
            print("Connected to Postgres target")
            await truncate_target(pg_conn)

            for table_name in TABLE_ORDER:
                rows = [normalize_row(table_name, row) for row in load_rows(sqlite_db, table_name)]
                await insert_rows(pg_conn, table_name, rows)

            await reset_sequences(pg_conn)
            await verify_counts(pg_conn, sqlite_db)
        finally:
            await pg_conn.close()
    finally:
        sqlite_db.close()


if __name__ == "__main__":
    asyncio.run(main())

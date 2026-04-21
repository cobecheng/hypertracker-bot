# Supabase Migration Plan

This document maps the current local SQLite deployment to a Supabase/Postgres-backed architecture.

## Current state

The bot and dashboard currently share one local SQLite database at `./data/hypertracker.db`.

Primary runtime responsibilities:

- The bot writes wallet fills, settings, and live snapshot cache.
- The local dashboard reads analytics and live snapshot data.
- The Mac mini is the only writer for Hyperliquid polling today.

Current row counts at audit time:

- `users`: 1
- `wallets`: 1
- `settings`: 1
- `wallet_fill_events`: 140,814
- `wallet_hourly_summary_state`: 1
- `wallet_live_snapshots`: 1
- `evm_tracked_addresses`: 0

## Scope

Tables that must migrate in phase 1:

- `users`
- `wallets`
- `settings`
- `wallet_fill_events`
- `wallet_hourly_summary_state`
- `wallet_live_snapshots`

Tables that can stay optional in phase 1:

- `evm_tracked_addresses`

## Target architecture

Phase 1 target:

- Bot stays on the Mac mini.
- Dashboard can still run locally at first.
- Both read and write against Supabase Postgres instead of local SQLite.

Phase 2 target:

- Dashboard is hosted remotely and reads from Supabase.
- Bot remains the single live data ingestor on the Mac mini.

## Migration strategy

### Step 1. Create Supabase project

User action required later:

- Create a Supabase project.
- Provide the Postgres connection string.
- Prefer the direct/session connection string for async server workloads.

### Step 2. Apply schema

Use `sql/supabase_schema.sql` against a fresh Supabase project.

Notes:

- JSON text columns become `jsonb`.
- integer booleans become proper `boolean`.
- ISO date strings become `timestamptz`.

### Step 3. Introduce Postgres adapter

Code work still needed:

- Add a Postgres-backed replacement for `core/database.py`.
- Preserve current method signatures where possible.
- Keep SQLite support during the transition using `DATABASE_BACKEND`.

Priority methods for first implementation:

- user/settings CRUD
- wallet CRUD
- `record_wallet_fill`
- hourly summary state methods
- `upsert_wallet_live_snapshot`
- dashboard query methods

### Step 4. Backfill existing data

Import order:

1. `users`
2. `wallets`
3. `settings`
4. `wallet_fill_events`
5. `wallet_hourly_summary_state`
6. `wallet_live_snapshots`
7. `evm_tracked_addresses` if used

Validation checks:

- row counts match
- latest `wallet_fill_events.event_time_ms` matches
- latest `wallet_live_snapshots.snapshot_time_ms` matches
- dashboard totals match for `1h`, `24h`, `7d`, `30d`

### Step 5. Switch bot runtime

- Set `DATABASE_BACKEND=postgres`
- Set `DATABASE_URL=...`
- restart the bot
- verify fill writes, live snapshots, and hourly summaries

### Step 6. Switch dashboard runtime

- point dashboard reads at Postgres
- verify wallet detail, live exposure, and summary windows

### Step 7. Remote hosting

Once the dashboard no longer depends on local SQLite:

- Vercel becomes viable for a frontend/API design that talks to Supabase
- or the current Python dashboard can be hosted on a persistent app host

## Risks to manage

- Supabase free projects can pause after inactivity.
- SQLite SQL must be adjusted for Postgres semantics.
- JSON parsing logic should move toward `jsonb` queries over time.
- backfill must preserve wallet IDs because downstream relationships depend on them.

## Recommended implementation order in code

1. Add dependency and Postgres adapter
2. Add database factory / backend selection
3. Port write paths
4. Port dashboard read paths
5. Run local verification against Supabase
6. Backfill historical data
7. Cut over production bot

## User inputs required later

When ready for the live migration, we will need:

- Supabase project connection string
- confirmation of which connection mode to use
- whether to keep the current local SQLite DB as rollback fallback during cutover

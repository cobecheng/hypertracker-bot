"""
Postgres database layer for HyperTracker Bot.
Backed by asyncpg and designed for Supabase/Postgres deployments.
"""
import hashlib
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import asyncpg

from core.evm_models import TrackedAddress, AddressType
from core.models import Wallet, WalletFilters, UserSettings, LiquidationFilters

logger = logging.getLogger(__name__)


def _load_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


class PostgresDatabase:
    """Async database manager using Postgres."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn: Optional[asyncpg.Connection] = None
        self._conn_lock = asyncio.Lock()

    async def connect(self):
        self.conn = await asyncpg.connect(self.database_url)
        await self._create_tables()
        logger.info("Postgres database connected")

    async def close(self):
        if self.conn:
            await self.conn.close()
            logger.info("Postgres database connection closed")

    async def _reconnect(self):
        """Re-establish a dropped postgres connection."""
        try:
            if self.conn and not self.conn.is_closed():
                await self.conn.close()
        except Exception:
            pass
        self.conn = await asyncpg.connect(self.database_url)
        logger.warning("Postgres connection was re-established after disconnect")

    async def _ensure_connection(self):
        if self.conn is None or self.conn.is_closed():
            await self._reconnect()

    async def _call(self, method_name: str, *args):
        async with self._conn_lock:
            await self._ensure_connection()
            method = getattr(self.conn, method_name)
            try:
                return await method(*args)
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError, OSError):
                await self._reconnect()
                method = getattr(self.conn, method_name)
                return await method(*args)

    async def _execute(self, *args):
        return await self._call("execute", *args)

    async def _fetchrow(self, *args):
        return await self._call("fetchrow", *args)

    async def _fetch(self, *args):
        return await self._call("fetch", *args)

    async def _fetchval(self, *args):
        return await self._call("fetchval", *args)

    async def _create_tables(self):
        """Validate schema presence. Schema creation is managed by sql/supabase_schema.sql."""
        try:
            exists = await self._fetchval(
                "select exists (select 1 from information_schema.tables where table_schema = 'public' and table_name = 'users')"
            )
            if not exists:
                raise RuntimeError("Supabase/Postgres schema is missing. Apply sql/supabase_schema.sql first.")
        except Exception as e:
            logger.error(f"Error validating Postgres schema: {e}")
            raise

    def _wallet_from_row(self, row) -> Wallet:
        return Wallet(
            id=row["id"],
            user_id=row["user_id"],
            address=row["address"],
            alias=row["alias"],
            filters=WalletFilters(**_load_json(row["filters_json"])),
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    def _tracked_address_from_row(self, row) -> TrackedAddress:
        return TrackedAddress(
            id=row["id"],
            user_id=row["user_id"],
            address=row["address"],
            label=row["label"],
            address_type=AddressType(row["address_type"]),
            token_contract=row["token_contract"],
            token_symbol=row["token_symbol"],
            min_value_usd=row["min_value_usd"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    async def create_user(self, telegram_id: int, username: Optional[str] = None) -> bool:
        try:
            await self._execute(
                """
                insert into public.users (telegram_id, username, created_at)
                values ($1, $2, $3)
                on conflict (telegram_id) do update set username = excluded.username
                """,
                telegram_id,
                username,
                datetime.utcnow(),
            )
            return True
        except Exception as e:
            logger.error(f"Error creating user {telegram_id}: {e}")
            return False

    async def get_user_settings(self, telegram_id: int) -> UserSettings:
        await self.create_user(telegram_id)
        row = await self._fetchrow(
            "select * from public.settings where user_id = $1",
            telegram_id,
        )
        if row:
            liq_filters = LiquidationFilters(**_load_json(row["liq_filters_json"]))
            liq_filters.enabled = bool(row["liq_monitor_enabled"])
            global_filters = None
            if row["global_wallet_filters_json"]:
                global_filters = WalletFilters(**_load_json(row["global_wallet_filters_json"]))
            return UserSettings(
                telegram_id=telegram_id,
                liquidation_filters=liq_filters,
                global_wallet_filters=global_filters,
            )

        default_filters = LiquidationFilters()
        await self._execute(
            """
            insert into public.settings (user_id, liq_monitor_enabled, liq_filters_json, global_wallet_filters_json)
            values ($1, $2, $3, $4)
            """,
            telegram_id,
            False,
            json.dumps(default_filters.model_dump()),
            None,
        )
        return UserSettings(telegram_id=telegram_id, liquidation_filters=default_filters, global_wallet_filters=None)

    async def update_liquidation_settings(self, telegram_id: int, filters: LiquidationFilters) -> bool:
        try:
            await self._execute(
                """
                insert into public.settings (user_id, liq_monitor_enabled, liq_filters_json, global_wallet_filters_json)
                values ($1, $2, $3, null)
                on conflict (user_id) do update set
                    liq_monitor_enabled = excluded.liq_monitor_enabled,
                    liq_filters_json = excluded.liq_filters_json
                """,
                telegram_id,
                filters.enabled,
                json.dumps(filters.model_dump()),
            )
            return True
        except Exception as e:
            logger.error(f"Error updating liquidation settings for {telegram_id}: {e}")
            return False

    async def update_global_wallet_filters(self, telegram_id: int, filters: Optional[WalletFilters]) -> bool:
        try:
            filters_json = json.dumps(filters.model_dump()) if filters else None
            await self._execute(
                """
                insert into public.settings (user_id, liq_monitor_enabled, liq_filters_json, global_wallet_filters_json)
                values ($1, false, '{}'::jsonb, $2)
                on conflict (user_id) do update set
                    global_wallet_filters_json = excluded.global_wallet_filters_json
                """,
                telegram_id,
                filters_json,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating global wallet filters for {telegram_id}: {e}")
            return False

    async def update_user_settings(self, telegram_id: int, settings: UserSettings) -> bool:
        try:
            await self._execute(
                """
                insert into public.settings (user_id, liq_monitor_enabled, liq_filters_json, global_wallet_filters_json)
                values ($1, $2, $3, $4)
                on conflict (user_id) do update set
                    liq_monitor_enabled = excluded.liq_monitor_enabled,
                    liq_filters_json = excluded.liq_filters_json,
                    global_wallet_filters_json = excluded.global_wallet_filters_json
                """,
                telegram_id,
                settings.liquidation_filters.enabled,
                json.dumps(settings.liquidation_filters.model_dump()),
                json.dumps(settings.global_wallet_filters.model_dump()) if settings.global_wallet_filters else None,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating user settings for {telegram_id}: {e}")
            return False

    async def add_wallet(self, wallet: Wallet) -> Optional[int]:
        try:
            row = await self._fetchrow(
                """
                insert into public.wallets (user_id, address, alias, filters_json, active, created_at)
                values ($1, $2, $3, $4, $5, $6)
                returning id
                """,
                wallet.user_id,
                wallet.address,
                wallet.alias,
                json.dumps(wallet.filters.model_dump()),
                wallet.active,
                datetime.utcnow(),
            )
            return row["id"]
        except asyncpg.UniqueViolationError:
            logger.warning(f"Wallet {wallet.address} already exists for user {wallet.user_id}")
            return None
        except Exception as e:
            logger.error(f"Error adding wallet: {e}")
            return None

    async def get_user_wallets(self, user_id: int) -> List[Wallet]:
        rows = await self._fetch(
            "select * from public.wallets where user_id = $1 order by created_at desc",
            user_id,
        )
        return [self._wallet_from_row(row) for row in rows]

    async def get_wallet_by_id(self, wallet_id: int) -> Optional[Wallet]:
        row = await self._fetchrow(
            "select * from public.wallets where id = $1",
            wallet_id,
        )
        return self._wallet_from_row(row) if row else None

    async def get_all_active_wallets(self) -> List[Wallet]:
        rows = await self._fetch("select * from public.wallets where active = true")
        return [self._wallet_from_row(row) for row in rows]

    async def get_wallet_live_dexes(self, wallet_id: int) -> List[str]:
        cutoff_ms = int((datetime.now(timezone.utc).timestamp() - 2592000) * 1000)
        rows = await self._fetch(
            """
            select distinct split_part(coin, ':', 1) as dex
            from public.wallet_fill_events
            where wallet_id = $1
              and position(':' in coin) > 0
              and event_time_ms >= $2
            order by dex
            """,
            wallet_id,
            cutoff_ms,
        )
        return [row["dex"] for row in rows if row["dex"]]

    async def update_wallet_filters(self, wallet_id: int, filters: WalletFilters) -> bool:
        try:
            await self._execute(
                "update public.wallets set filters_json = $1 where id = $2",
                json.dumps(filters.model_dump()),
                wallet_id,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating wallet filters: {e}")
            return False

    async def update_wallet_active(self, wallet_id: int, active: bool) -> bool:
        try:
            await self._execute(
                "update public.wallets set active = $1 where id = $2",
                active,
                wallet_id,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating wallet active status: {e}")
            return False

    async def delete_wallet(self, wallet_id: int, user_id: int) -> bool:
        try:
            result = await self._execute(
                "delete from public.wallets where id = $1 and user_id = $2",
                wallet_id,
                user_id,
            )
            return result.split()[-1] != "0"
        except Exception as e:
            logger.error(f"Error deleting wallet: {e}")
            return False

    async def get_all_users(self) -> List[UserSettings]:
        try:
            rows = await self._fetch("select telegram_id from public.users")
            return [await self.get_user_settings(row["telegram_id"]) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    async def record_wallet_fill(self, wallet: Wallet, fill, is_close: bool) -> bool:
        if wallet.id is None:
            logger.warning("Skipping fill persistence for wallet without database ID")
            return False
        try:
            price = float(fill.px)
            size = float(fill.sz)
            fee = float(fill.fee) if fill.fee is not None else None
            notional = price * size
            event_time_ms = int(fill.time)
            event_time_iso = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc)
            raw_key = "|".join([
                str(wallet.id),
                wallet.address.lower(),
                fill.coin,
                fill.side,
                f"{price:.10f}",
                f"{size:.10f}",
                str(event_time_ms),
                fill.hash or "",
                fill.dir or "",
            ])
            event_id = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
            await self._execute(
                """
                insert into public.wallet_fill_events (
                    wallet_id, user_id, wallet_address, coin, side, price, size,
                    notional_usd, event_time_ms, event_time_iso, hash, fee,
                    liquidation, is_close, dir, event_id, created_at
                )
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                on conflict (event_id) do nothing
                """,
                wallet.id,
                wallet.user_id,
                wallet.address.lower(),
                fill.coin,
                fill.side,
                price,
                size,
                notional,
                event_time_ms,
                event_time_iso,
                fill.hash,
                fee,
                bool(fill.liquidation),
                bool(is_close),
                fill.dir,
                event_id,
                datetime.utcnow(),
            )
            return True
        except Exception as e:
            logger.error(f"Error recording wallet fill for wallet {wallet.id}: {e}")
            return False

    async def get_last_summary_hour_start_ms(self, wallet_id: int) -> Optional[int]:
        row = await self._fetchrow(
            "select last_completed_hour_start_ms from public.wallet_hourly_summary_state where wallet_id = $1",
            wallet_id,
        )
        return row["last_completed_hour_start_ms"] if row else None

    async def mark_summary_hour_processed(self, wallet_id: int, hour_start_ms: int) -> bool:
        try:
            await self._execute(
                """
                insert into public.wallet_hourly_summary_state (wallet_id, last_completed_hour_start_ms, updated_at)
                values ($1, $2, $3)
                on conflict (wallet_id) do update set
                    last_completed_hour_start_ms = excluded.last_completed_hour_start_ms,
                    updated_at = excluded.updated_at
                """,
                wallet_id,
                hour_start_ms,
                datetime.utcnow(),
            )
            return True
        except Exception as e:
            logger.error(f"Error marking summary hour for wallet {wallet_id}: {e}")
            return False

    async def get_wallet_fill_summary(self, wallet_id: int, start_time_ms: int, end_time_ms: int) -> dict:
        summary = {"total_fills": 0, "total_buy_usd": 0.0, "total_sell_usd": 0.0, "net_flow_usd": 0.0, "assets": []}
        totals = await self._fetchrow(
            """
            select
                count(*) as total_fills,
                coalesce(sum(case when side = 'B' then notional_usd else 0 end), 0) as total_buy_usd,
                coalesce(sum(case when side = 'A' then notional_usd else 0 end), 0) as total_sell_usd
            from public.wallet_fill_events
            where wallet_id = $1 and event_time_ms >= $2 and event_time_ms < $3
            """,
            wallet_id,
            start_time_ms,
            end_time_ms,
        )
        if totals:
            summary["total_fills"] = totals["total_fills"] or 0
            summary["total_buy_usd"] = float(totals["total_buy_usd"] or 0)
            summary["total_sell_usd"] = float(totals["total_sell_usd"] or 0)
            summary["net_flow_usd"] = summary["total_buy_usd"] - summary["total_sell_usd"]
        rows = await self._fetch(
            """
            select
                coin,
                count(*) as fills_count,
                coalesce(sum(case when side = 'B' then notional_usd else 0 end), 0) as gross_buy_usd,
                coalesce(sum(case when side = 'A' then notional_usd else 0 end), 0) as gross_sell_usd,
                coalesce(sum(case when side = 'B' then size else -size end), 0) as net_size
            from public.wallet_fill_events
            where wallet_id = $1 and event_time_ms >= $2 and event_time_ms < $3
            group by coin
            order by abs(
                coalesce(sum(case when side = 'B' then notional_usd else 0 end), 0) -
                coalesce(sum(case when side = 'A' then notional_usd else 0 end), 0)
            ) desc, fills_count desc
            """,
            wallet_id,
            start_time_ms,
            end_time_ms,
        )
        for row in rows:
            gross_buy_usd = float(row["gross_buy_usd"] or 0)
            gross_sell_usd = float(row["gross_sell_usd"] or 0)
            summary["assets"].append({
                "coin": row["coin"],
                "fills_count": row["fills_count"],
                "gross_buy_usd": gross_buy_usd,
                "gross_sell_usd": gross_sell_usd,
                "net_flow_usd": gross_buy_usd - gross_sell_usd,
                "net_size": float(row["net_size"] or 0),
            })
        return summary

    async def delete_fill_events_before(self, cutoff_time_ms: int) -> bool:
        try:
            await self._execute("delete from public.wallet_fill_events where event_time_ms < $1", cutoff_time_ms)
            return True
        except Exception as e:
            logger.error(f"Error deleting old fill events: {e}")
            return False

    async def upsert_wallet_live_snapshot(self, wallet: Wallet, snapshot_time_ms: int, positions: list[dict], raw_snapshot: dict, account_value: float, total_notional_usd: float, total_margin_used: float, withdrawable: float) -> bool:
        if wallet.id is None:
            return False
        long_count = sum(1 for p in positions if p.get("direction") == "long")
        short_count = sum(1 for p in positions if p.get("direction") == "short")
        bias = "long" if long_count > short_count else "short" if short_count > long_count else "flat"
        snapshot_time_iso = datetime.fromtimestamp(snapshot_time_ms / 1000, tz=timezone.utc)
        try:
            await self._execute(
                """
                insert into public.wallet_live_snapshots (
                    wallet_id, user_id, wallet_address, account_value,
                    total_notional_usd, total_margin_used, withdrawable,
                    positions_count, long_positions_count, short_positions_count,
                    net_exposure_bias, positions_json, raw_snapshot_json,
                    snapshot_time_ms, snapshot_time_iso, updated_at
                )
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                on conflict (wallet_id) do update set
                    user_id = excluded.user_id,
                    wallet_address = excluded.wallet_address,
                    account_value = excluded.account_value,
                    total_notional_usd = excluded.total_notional_usd,
                    total_margin_used = excluded.total_margin_used,
                    withdrawable = excluded.withdrawable,
                    positions_count = excluded.positions_count,
                    long_positions_count = excluded.long_positions_count,
                    short_positions_count = excluded.short_positions_count,
                    net_exposure_bias = excluded.net_exposure_bias,
                    positions_json = excluded.positions_json,
                    raw_snapshot_json = excluded.raw_snapshot_json,
                    snapshot_time_ms = excluded.snapshot_time_ms,
                    snapshot_time_iso = excluded.snapshot_time_iso,
                    updated_at = excluded.updated_at
                """,
                wallet.id, wallet.user_id, wallet.address.lower(), account_value,
                total_notional_usd, total_margin_used, withdrawable,
                len(positions), long_count, short_count, bias,
                json.dumps(positions), json.dumps(raw_snapshot),
                snapshot_time_ms, snapshot_time_iso, datetime.utcnow(),
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting live snapshot for wallet {wallet.id}: {e}")
            return False

    async def get_live_dashboard_overview(self) -> dict:
        row = await self._fetchrow(
            """
            select
                count(*) as wallets_with_snapshot,
                coalesce(sum(account_value), 0) as total_account_value,
                coalesce(sum(total_notional_usd), 0) as total_notional_usd,
                coalesce(sum(case when net_exposure_bias = 'long' then 1 else 0 end), 0) as net_long_wallets,
                coalesce(sum(case when net_exposure_bias = 'short' then 1 else 0 end), 0) as net_short_wallets,
                coalesce(sum(positions_count), 0) as total_open_positions,
                max(snapshot_time_ms) as latest_snapshot_time_ms
            from public.wallet_live_snapshots
            """
        )
        return {
            "wallets_with_snapshot": row["wallets_with_snapshot"] or 0,
            "total_account_value": float(row["total_account_value"] or 0),
            "total_notional_usd": float(row["total_notional_usd"] or 0),
            "net_long_wallets": row["net_long_wallets"] or 0,
            "net_short_wallets": row["net_short_wallets"] or 0,
            "total_open_positions": row["total_open_positions"] or 0,
            "latest_snapshot_time_ms": row["latest_snapshot_time_ms"],
        }

    async def get_live_asset_exposure(self, limit: int = 25) -> List[dict]:
        rows = await self._fetch("select wallet_address, positions_json from public.wallet_live_snapshots")
        exposures: dict[str, dict] = {}
        for row in rows:
            positions = _load_json(row["positions_json"])
            seen_assets = set()
            for position in positions:
                coin = position.get("coin")
                if not coin:
                    continue
                data = exposures.setdefault(coin, {"coin": coin, "wallets_count": 0, "long_usd": 0.0, "short_usd": 0.0, "net_usd": 0.0})
                if coin not in seen_assets:
                    data["wallets_count"] += 1
                    seen_assets.add(coin)
                notional = float(position.get("position_notional_usd") or 0)
                direction = position.get("direction")
                if direction == "long":
                    data["long_usd"] += notional
                    data["net_usd"] += notional
                elif direction == "short":
                    data["short_usd"] += notional
                    data["net_usd"] -= notional
        return sorted(exposures.values(), key=lambda item: abs(item["net_usd"]), reverse=True)[:limit]

    async def get_wallet_live_snapshot(self, wallet_id: int) -> Optional[dict]:
        row = await self._fetchrow("select * from public.wallet_live_snapshots where wallet_id = $1", wallet_id)
        if not row:
            return None
        return {
            "wallet_id": row["wallet_id"],
            "user_id": row["user_id"],
            "wallet_address": row["wallet_address"],
            "account_value": float(row["account_value"] or 0),
            "total_notional_usd": float(row["total_notional_usd"] or 0),
            "total_margin_used": float(row["total_margin_used"] or 0),
            "withdrawable": float(row["withdrawable"] or 0),
            "positions_count": row["positions_count"] or 0,
            "long_positions_count": row["long_positions_count"] or 0,
            "short_positions_count": row["short_positions_count"] or 0,
            "net_exposure_bias": row["net_exposure_bias"],
            "positions": _load_json(row["positions_json"]),
            "snapshot_time_ms": row["snapshot_time_ms"],
        }

    async def get_dashboard_overview(self, start_time_ms: int) -> dict:
        row = await self._fetchrow(
            """
            select
                count(distinct w.id) as tracked_wallets,
                count(distinct case when e.id is not null then w.id end) as active_wallets,
                count(distinct e.coin) as active_assets,
                count(e.id) as total_fills,
                coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) as total_buy_usd,
                coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0) as total_sell_usd
            from public.wallets w
            left join public.wallet_fill_events e
              on e.wallet_id = w.id and e.event_time_ms >= $1
            where w.active = true
            """,
            start_time_ms,
        )
        buy = float(row["total_buy_usd"] or 0)
        sell = float(row["total_sell_usd"] or 0)
        return {
            "tracked_wallets": row["tracked_wallets"] or 0,
            "active_wallets": row["active_wallets"] or 0,
            "active_assets": row["active_assets"] or 0,
            "total_fills": row["total_fills"] or 0,
            "total_buy_usd": buy,
            "total_sell_usd": sell,
            "net_flow_usd": buy - sell,
        }

    async def get_dashboard_asset_flows(self, start_time_ms: int, limit: int = 25) -> List[dict]:
        rows = await self._fetch(
            """
            select
                e.coin,
                count(*) as fills_count,
                count(distinct e.wallet_id) as wallets_count,
                coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) as buy_usd,
                coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0) as sell_usd
            from public.wallet_fill_events e
            inner join public.wallets w on w.id = e.wallet_id
            where w.active = true and e.event_time_ms >= $1
            group by e.coin
            order by abs(
                coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) -
                coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0)
            ) desc, fills_count desc
            limit $2
            """,
            start_time_ms,
            limit,
        )
        assets = []
        for row in rows:
            buy = float(row["buy_usd"] or 0)
            sell = float(row["sell_usd"] or 0)
            assets.append({"coin": row["coin"], "fills_count": row["fills_count"], "wallets_count": row["wallets_count"], "buy_usd": buy, "sell_usd": sell, "net_flow_usd": buy - sell})
        return assets

    async def get_dashboard_wallet_summaries(self, start_time_ms: int, limit: int = 100) -> List[dict]:
        rows = await self._fetch(
            """
            select
                w.id, w.user_id, w.address, w.alias,
                count(e.id) as fills_count,
                count(distinct e.coin) as assets_count,
                max(e.event_time_ms) as last_event_time_ms,
                coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) as buy_usd,
                coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0) as sell_usd
            from public.wallets w
            left join public.wallet_fill_events e on e.wallet_id = w.id and e.event_time_ms >= $1
            where w.active = true
            group by w.id, w.user_id, w.address, w.alias, w.created_at
            order by abs(
                coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) -
                coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0)
            ) desc, fills_count desc, w.created_at desc
            limit $2
            """,
            start_time_ms,
            limit,
        )
        wallets = []
        for row in rows:
            buy = float(row["buy_usd"] or 0)
            sell = float(row["sell_usd"] or 0)
            wallets.append({
                "id": row["id"], "user_id": row["user_id"], "address": row["address"], "alias": row["alias"],
                "fills_count": row["fills_count"] or 0, "assets_count": row["assets_count"] or 0,
                "last_event_time_ms": row["last_event_time_ms"], "buy_usd": buy, "sell_usd": sell, "net_flow_usd": buy - sell,
            })
        for wallet in wallets:
            wallet["live"] = await self.get_wallet_live_snapshot(wallet["id"])
        return wallets

    async def get_recent_fill_events(self, start_time_ms: int, limit: int = 50) -> List[dict]:
        rows = await self._fetch(
            """
            select e.wallet_id, w.alias, w.address, e.coin, e.side, e.price, e.size, e.notional_usd, e.event_time_ms, e.dir
            from public.wallet_fill_events e
            inner join public.wallets w on w.id = e.wallet_id
            where w.active = true and e.event_time_ms >= $1
            order by e.event_time_ms desc, e.id desc
            limit $2
            """,
            start_time_ms,
            limit,
        )
        return [{
            "wallet_id": row["wallet_id"], "alias": row["alias"], "address": row["address"], "coin": row["coin"],
            "side": row["side"], "price": float(row["price"]), "size": float(row["size"]),
            "notional_usd": float(row["notional_usd"]), "event_time_ms": row["event_time_ms"], "dir": row["dir"],
        } for row in rows]

    async def get_wallet_dashboard_detail(self, wallet_id: int, start_time_ms: int) -> Optional[dict]:
        wallet_row = await self._fetchrow("select id, user_id, address, alias, active from public.wallets where id = $1", wallet_id)
        if not wallet_row:
            return None
        summary_row = await self._fetchrow(
            """
            select count(*) as fills_count, count(distinct coin) as assets_count, max(event_time_ms) as last_event_time_ms,
                   coalesce(sum(case when side='B' then notional_usd else 0 end),0) as buy_usd,
                   coalesce(sum(case when side='A' then notional_usd else 0 end),0) as sell_usd
            from public.wallet_fill_events where wallet_id = $1 and event_time_ms >= $2
            """, wallet_id, start_time_ms)
        asset_rows = await self._fetch(
            """
            select coin, count(*) as fills_count,
                   coalesce(sum(case when side='B' then notional_usd else 0 end),0) as buy_usd,
                   coalesce(sum(case when side='A' then notional_usd else 0 end),0) as sell_usd
            from public.wallet_fill_events
            where wallet_id = $1 and event_time_ms >= $2
            group by coin
            order by abs(
                coalesce(sum(case when side='B' then notional_usd else 0 end),0) -
                coalesce(sum(case when side='A' then notional_usd else 0 end),0)
            ) desc, fills_count desc
            """, wallet_id, start_time_ms)
        recent_rows = await self._fetch(
            """
            select coin, side, price, size, notional_usd, event_time_ms, dir
            from public.wallet_fill_events
            where wallet_id = $1 and event_time_ms >= $2
            order by event_time_ms desc, id desc
            limit 20
            """, wallet_id, start_time_ms)
        buy = float(summary_row["buy_usd"] or 0)
        sell = float(summary_row["sell_usd"] or 0)
        return {
            "wallet": {"id": wallet_row["id"], "user_id": wallet_row["user_id"], "address": wallet_row["address"], "alias": wallet_row["alias"], "active": bool(wallet_row["active"])},
            "summary": {"fills_count": summary_row["fills_count"] or 0, "assets_count": summary_row["assets_count"] or 0, "last_event_time_ms": summary_row["last_event_time_ms"], "buy_usd": buy, "sell_usd": sell, "net_flow_usd": buy - sell},
            "live": await self.get_wallet_live_snapshot(wallet_id),
            "assets": [{"coin": row["coin"], "fills_count": row["fills_count"], "buy_usd": float(row["buy_usd"] or 0), "sell_usd": float(row["sell_usd"] or 0), "net_flow_usd": float(row["buy_usd"] or 0) - float(row["sell_usd"] or 0)} for row in asset_rows],
            "recent_fills": [{"coin": row["coin"], "side": row["side"], "price": float(row["price"]), "size": float(row["size"]), "notional_usd": float(row["notional_usd"]), "event_time_ms": row["event_time_ms"], "dir": row["dir"]} for row in recent_rows],
        }

    async def add_evm_address(self, tracked_address: TrackedAddress) -> Optional[int]:
        try:
            row = await self._fetchrow(
                """
                insert into public.evm_tracked_addresses (
                    user_id, address, label, address_type, token_contract,
                    token_symbol, min_value_usd, active, created_at
                )
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                returning id
                """,
                tracked_address.user_id,
                tracked_address.address.lower(),
                tracked_address.label,
                tracked_address.address_type.value,
                tracked_address.token_contract.lower() if tracked_address.token_contract else None,
                tracked_address.token_symbol,
                tracked_address.min_value_usd,
                tracked_address.active,
                datetime.utcnow(),
            )
            return row["id"]
        except asyncpg.UniqueViolationError:
            logger.warning(f"Address {tracked_address.address} already tracked by user {tracked_address.user_id}")
            return None
        except Exception as e:
            logger.error(f"Error adding EVM address: {e}")
            return None

    async def get_user_evm_addresses(self, user_id: int) -> List[TrackedAddress]:
        rows = await self._fetch("select * from public.evm_tracked_addresses where user_id = $1 order by created_at desc", user_id)
        return [self._tracked_address_from_row(row) for row in rows]

    async def get_all_active_evm_addresses(self) -> List[TrackedAddress]:
        rows = await self._fetch("select * from public.evm_tracked_addresses where active = true")
        return [self._tracked_address_from_row(row) for row in rows]

    async def get_users_tracking_evm_address(self, address: str) -> List[TrackedAddress]:
        rows = await self._fetch("select * from public.evm_tracked_addresses where address = $1 and active = true", address.lower())
        return [self._tracked_address_from_row(row) for row in rows]

    async def update_evm_address_active(self, address_id: int, active: bool) -> bool:
        try:
            await self._execute("update public.evm_tracked_addresses set active = $1 where id = $2", active, address_id)
            return True
        except Exception as e:
            logger.error(f"Error updating EVM address active status: {e}")
            return False

    async def delete_evm_address(self, address_id: int, user_id: int) -> bool:
        try:
            result = await self._execute("delete from public.evm_tracked_addresses where id = $1 and user_id = $2", address_id, user_id)
            return result.split()[-1] != "0"
        except Exception as e:
            logger.error(f"Error deleting EVM address: {e}")
            return False

    async def get_stats(self) -> dict:
        total_users = await self._fetchval("select count(*) from public.users")
        total_wallets = await self._fetchval("select count(*) from public.wallets")
        active_wallets = await self._fetchval("select count(*) from public.wallets where active = true")
        active_evm_addresses = await self._fetchval("select count(*) from public.evm_tracked_addresses where active = true")
        return {
            "total_users": total_users,
            "total_wallets": total_wallets,
            "active_wallets": active_wallets,
            "active_evm_addresses": active_evm_addresses,
        }

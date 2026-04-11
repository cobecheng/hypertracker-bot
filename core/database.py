"""
Database layer using aiosqlite for HyperTracker Bot.
Handles all database operations with async/await support.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite

from core.models import Wallet, WalletFilters, UserSettings, LiquidationFilters
from core.evm_models import TrackedAddress, AddressType

logger = logging.getLogger(__name__)


class Database:
    """Async database manager using SQLite."""
    
    def __init__(self, db_path: str):
        """Initialize database with path."""
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """Connect to the database and create tables if needed."""
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"Database connected: {self.db_path}")
    
    async def close(self):
        """Close database connection."""
        if self.conn:
            await self.conn.close()
            logger.info("Database connection closed")
    
    async def _create_tables(self):
        """Create database tables if they don't exist."""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TEXT NOT NULL
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                alias TEXT,
                filters_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                UNIQUE(user_id, address)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                liq_monitor_enabled INTEGER NOT NULL DEFAULT 0,
                liq_filters_json TEXT NOT NULL,
                global_wallet_filters_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        # Migration: Add global_wallet_filters_json column if it doesn't exist
        try:
            cursor = await self.conn.execute("PRAGMA table_info(settings)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'global_wallet_filters_json' not in column_names:
                logger.info("Migrating database: Adding global_wallet_filters_json column to settings table")
                await self.conn.execute("""
                    ALTER TABLE settings ADD COLUMN global_wallet_filters_json TEXT
                """)
                await self.conn.commit()
                logger.info("Migration completed successfully")
        except Exception as e:
            logger.error(f"Error during migration: {e}")

        # Create indexes for faster queries
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallets_user_id ON wallets(user_id)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallets_address ON wallets(address)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallets_active ON wallets(active)
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_fill_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                coin TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                notional_usd REAL NOT NULL,
                event_time_ms INTEGER NOT NULL,
                event_time_iso TEXT NOT NULL,
                hash TEXT,
                fee REAL,
                liquidation INTEGER NOT NULL DEFAULT 0,
                is_close INTEGER NOT NULL DEFAULT 0,
                dir TEXT,
                event_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (wallet_id) REFERENCES wallets(id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fill_events_wallet_time
            ON wallet_fill_events(wallet_id, event_time_ms)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fill_events_user_time
            ON wallet_fill_events(user_id, event_time_ms)
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_hourly_summary_state (
                wallet_id INTEGER PRIMARY KEY,
                last_completed_hour_start_ms INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (wallet_id) REFERENCES wallets(id)
            )
        """)

        # EVM tracking table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS evm_tracked_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                label TEXT NOT NULL,
                address_type TEXT NOT NULL,
                token_contract TEXT,
                token_symbol TEXT,
                min_value_usd REAL NOT NULL DEFAULT 0.0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                UNIQUE(user_id, address)
            )
        """)

        # EVM indexes
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_evm_address ON evm_tracked_addresses(address)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_evm_active ON evm_tracked_addresses(active)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_evm_user_id ON evm_tracked_addresses(user_id)
        """)

        await self.conn.commit()
    
    # User operations
    async def create_user(self, telegram_id: int, username: Optional[str] = None) -> bool:
        """Create a new user or update existing."""
        try:
            await self.conn.execute("""
                INSERT INTO users (telegram_id, username, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username
            """, (telegram_id, username, datetime.utcnow().isoformat()))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error creating user {telegram_id}: {e}")
            return False
    
    async def get_user_settings(self, telegram_id: int) -> UserSettings:
        """Get user settings, create if doesn't exist."""
        await self.create_user(telegram_id)

        cursor = await self.conn.execute("""
            SELECT * FROM settings WHERE user_id = ?
        """, (telegram_id,))
        row = await cursor.fetchone()

        if row:
            liq_filters = LiquidationFilters(**json.loads(row['liq_filters_json']))
            liq_filters.enabled = bool(row['liq_monitor_enabled'])

            # Load global wallet filters if they exist
            global_filters = None
            if row['global_wallet_filters_json']:
                global_filters = WalletFilters(**json.loads(row['global_wallet_filters_json']))

            return UserSettings(
                telegram_id=telegram_id,
                liquidation_filters=liq_filters,
                global_wallet_filters=global_filters
            )
        else:
            # Create default settings
            default_filters = LiquidationFilters()
            await self.conn.execute("""
                INSERT INTO settings (user_id, liq_monitor_enabled, liq_filters_json, global_wallet_filters_json)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, 0, json.dumps(default_filters.model_dump()), None))
            await self.conn.commit()
            return UserSettings(telegram_id=telegram_id, liquidation_filters=default_filters, global_wallet_filters=None)
    
    async def update_liquidation_settings(self, telegram_id: int, filters: LiquidationFilters) -> bool:
        """Update liquidation monitoring settings."""
        try:
            await self.conn.execute("""
                INSERT INTO settings (user_id, liq_monitor_enabled, liq_filters_json, global_wallet_filters_json)
                VALUES (?, ?, ?, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    liq_monitor_enabled=excluded.liq_monitor_enabled,
                    liq_filters_json=excluded.liq_filters_json
            """, (telegram_id, int(filters.enabled), json.dumps(filters.model_dump())))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating liquidation settings for {telegram_id}: {e}")
            return False

    async def update_global_wallet_filters(self, telegram_id: int, filters: Optional[WalletFilters]) -> bool:
        """Update global wallet filters."""
        try:
            filters_json = json.dumps(filters.model_dump()) if filters else None
            await self.conn.execute("""
                INSERT INTO settings (user_id, liq_monitor_enabled, liq_filters_json, global_wallet_filters_json)
                VALUES (?, 0, '{}', ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    global_wallet_filters_json=excluded.global_wallet_filters_json
            """, (telegram_id, filters_json))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating global wallet filters for {telegram_id}: {e}")
            return False
    
    # Wallet operations
    async def add_wallet(self, wallet: Wallet) -> Optional[int]:
        """Add a new wallet to track. Returns wallet ID or None on error."""
        try:
            cursor = await self.conn.execute("""
                INSERT INTO wallets (user_id, address, alias, filters_json, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                wallet.user_id,
                wallet.address,
                wallet.alias,
                json.dumps(wallet.filters.model_dump()),
                int(wallet.active),
                datetime.utcnow().isoformat()
            ))
            await self.conn.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            logger.warning(f"Wallet {wallet.address} already exists for user {wallet.user_id}")
            return None
        except Exception as e:
            logger.error(f"Error adding wallet: {e}")
            return None
    
    async def get_user_wallets(self, user_id: int) -> List[Wallet]:
        """Get all wallets for a user."""
        cursor = await self.conn.execute("""
            SELECT * FROM wallets WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        rows = await cursor.fetchall()
        
        wallets = []
        for row in rows:
            filters = WalletFilters(**json.loads(row['filters_json']))
            wallets.append(Wallet(
                id=row['id'],
                user_id=row['user_id'],
                address=row['address'],
                alias=row['alias'],
                filters=filters,
                active=bool(row['active']),
                created_at=datetime.fromisoformat(row['created_at'])
            ))
        return wallets
    
    async def get_wallet_by_id(self, wallet_id: int) -> Optional[Wallet]:
        """Get a specific wallet by ID."""
        cursor = await self.conn.execute("""
            SELECT * FROM wallets WHERE id = ?
        """, (wallet_id,))
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        filters = WalletFilters(**json.loads(row['filters_json']))
        return Wallet(
            id=row['id'],
            user_id=row['user_id'],
            address=row['address'],
            alias=row['alias'],
            filters=filters,
            active=bool(row['active']),
            created_at=datetime.fromisoformat(row['created_at'])
        )
    
    async def get_all_active_wallets(self) -> List[Wallet]:
        """Get all active wallets across all users."""
        cursor = await self.conn.execute("""
            SELECT * FROM wallets WHERE active = 1
        """)
        rows = await cursor.fetchall()
        
        wallets = []
        for row in rows:
            filters = WalletFilters(**json.loads(row['filters_json']))
            wallets.append(Wallet(
                id=row['id'],
                user_id=row['user_id'],
                address=row['address'],
                alias=row['alias'],
                filters=filters,
                active=bool(row['active']),
                created_at=datetime.fromisoformat(row['created_at'])
            ))
        return wallets
    
    async def update_wallet_filters(self, wallet_id: int, filters: WalletFilters) -> bool:
        """Update wallet filters."""
        try:
            await self.conn.execute("""
                UPDATE wallets SET filters_json = ? WHERE id = ?
            """, (json.dumps(filters.model_dump()), wallet_id))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating wallet filters: {e}")
            return False
    
    async def update_wallet_active(self, wallet_id: int, active: bool) -> bool:
        """Toggle wallet active status."""
        try:
            await self.conn.execute("""
                UPDATE wallets SET active = ? WHERE id = ?
            """, (int(active), wallet_id))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating wallet active status: {e}")
            return False
    
    async def delete_wallet(self, wallet_id: int, user_id: int) -> bool:
        """Delete a wallet (must belong to user)."""
        try:
            cursor = await self.conn.execute("""
                DELETE FROM wallets WHERE id = ? AND user_id = ?
            """, (wallet_id, user_id))
            await self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting wallet: {e}")
            return False
    
    async def get_all_users(self) -> List[UserSettings]:
        """Get all users from database."""
        try:
            cursor = await self.conn.execute("SELECT telegram_id FROM users")
            rows = await cursor.fetchall()
            users = []
            for row in rows:
                user_settings = await self.get_user_settings(row['telegram_id'])
                users.append(user_settings)
            return users
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    async def record_wallet_fill(self, wallet: Wallet, fill, is_close: bool) -> bool:
        """Persist a fill event for later summary rollups."""
        if wallet.id is None:
            logger.warning("Skipping fill persistence for wallet without database ID")
            return False

        try:
            price = float(fill.px)
            size = float(fill.sz)
            fee = float(fill.fee) if fill.fee is not None else None
            notional = price * size
            event_time_ms = int(fill.time)
            event_time_iso = datetime.fromtimestamp(
                event_time_ms / 1000,
                tz=timezone.utc,
            ).isoformat()
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

            await self.conn.execute("""
                INSERT OR IGNORE INTO wallet_fill_events (
                    wallet_id, user_id, wallet_address, coin, side, price, size,
                    notional_usd, event_time_ms, event_time_iso, hash, fee,
                    liquidation, is_close, dir, event_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
                int(fill.liquidation),
                int(is_close),
                fill.dir,
                event_id,
                datetime.utcnow().isoformat(),
            ))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error recording wallet fill for wallet {wallet.id}: {e}")
            return False

    async def get_last_summary_hour_start_ms(self, wallet_id: int) -> Optional[int]:
        """Get the last completed hour start already processed for a wallet."""
        cursor = await self.conn.execute("""
            SELECT last_completed_hour_start_ms
            FROM wallet_hourly_summary_state
            WHERE wallet_id = ?
        """, (wallet_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return row["last_completed_hour_start_ms"]

    async def mark_summary_hour_processed(self, wallet_id: int, hour_start_ms: int) -> bool:
        """Mark a completed hour as processed for summary generation."""
        try:
            await self.conn.execute("""
                INSERT INTO wallet_hourly_summary_state (
                    wallet_id, last_completed_hour_start_ms, updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(wallet_id) DO UPDATE SET
                    last_completed_hour_start_ms = excluded.last_completed_hour_start_ms,
                    updated_at = excluded.updated_at
            """, (
                wallet_id,
                hour_start_ms,
                datetime.utcnow().isoformat(),
            ))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error marking summary hour for wallet {wallet_id}: {e}")
            return False

    async def get_wallet_fill_summary(
        self,
        wallet_id: int,
        start_time_ms: int,
        end_time_ms: int,
    ) -> dict:
        """Aggregate fills for a wallet over a time window."""
        summary = {
            "total_fills": 0,
            "total_buy_usd": 0.0,
            "total_sell_usd": 0.0,
            "net_flow_usd": 0.0,
            "assets": [],
        }

        totals_cursor = await self.conn.execute("""
            SELECT
                COUNT(*) AS total_fills,
                COALESCE(SUM(CASE WHEN side = 'B' THEN notional_usd ELSE 0 END), 0) AS total_buy_usd,
                COALESCE(SUM(CASE WHEN side = 'A' THEN notional_usd ELSE 0 END), 0) AS total_sell_usd
            FROM wallet_fill_events
            WHERE wallet_id = ?
              AND event_time_ms >= ?
              AND event_time_ms < ?
        """, (wallet_id, start_time_ms, end_time_ms))
        totals_row = await totals_cursor.fetchone()

        if totals_row:
            summary["total_fills"] = totals_row["total_fills"] or 0
            summary["total_buy_usd"] = float(totals_row["total_buy_usd"] or 0)
            summary["total_sell_usd"] = float(totals_row["total_sell_usd"] or 0)
            summary["net_flow_usd"] = summary["total_buy_usd"] - summary["total_sell_usd"]

        assets_cursor = await self.conn.execute("""
            SELECT
                coin,
                COUNT(*) AS fills_count,
                COALESCE(SUM(CASE WHEN side = 'B' THEN notional_usd ELSE 0 END), 0) AS gross_buy_usd,
                COALESCE(SUM(CASE WHEN side = 'A' THEN notional_usd ELSE 0 END), 0) AS gross_sell_usd,
                COALESCE(SUM(CASE WHEN side = 'B' THEN size ELSE -size END), 0) AS net_size
            FROM wallet_fill_events
            WHERE wallet_id = ?
              AND event_time_ms >= ?
              AND event_time_ms < ?
            GROUP BY coin
            ORDER BY ABS(
                COALESCE(SUM(CASE WHEN side = 'B' THEN notional_usd ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN side = 'A' THEN notional_usd ELSE 0 END), 0)
            ) DESC,
            fills_count DESC
        """, (wallet_id, start_time_ms, end_time_ms))
        asset_rows = await assets_cursor.fetchall()

        for row in asset_rows:
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
        """Delete old persisted fill events to keep the database compact."""
        try:
            await self.conn.execute("""
                DELETE FROM wallet_fill_events
                WHERE event_time_ms < ?
            """, (cutoff_time_ms,))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting old fill events: {e}")
            return False

    # EVM tracking operations
    async def add_evm_address(self, tracked_address: TrackedAddress) -> Optional[int]:
        """Add a new EVM address to track. Returns address ID or None on error."""
        try:
            cursor = await self.conn.execute("""
                INSERT INTO evm_tracked_addresses (
                    user_id, address, label, address_type, token_contract,
                    token_symbol, min_value_usd, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tracked_address.user_id,
                tracked_address.address.lower(),  # Store lowercase for consistency
                tracked_address.label,
                tracked_address.address_type.value,
                tracked_address.token_contract.lower() if tracked_address.token_contract else None,
                tracked_address.token_symbol,
                tracked_address.min_value_usd,
                int(tracked_address.active),
                datetime.utcnow().isoformat()
            ))
            await self.conn.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            logger.warning(f"Address {tracked_address.address} already tracked by user {tracked_address.user_id}")
            return None
        except Exception as e:
            logger.error(f"Error adding EVM address: {e}")
            return None

    async def get_user_evm_addresses(self, user_id: int) -> List[TrackedAddress]:
        """Get all EVM addresses tracked by a user."""
        cursor = await self.conn.execute("""
            SELECT * FROM evm_tracked_addresses WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        rows = await cursor.fetchall()

        addresses = []
        for row in rows:
            addresses.append(TrackedAddress(
                id=row['id'],
                user_id=row['user_id'],
                address=row['address'],
                label=row['label'],
                address_type=AddressType(row['address_type']),
                token_contract=row['token_contract'],
                token_symbol=row['token_symbol'],
                min_value_usd=row['min_value_usd'],
                active=bool(row['active']),
                created_at=datetime.fromisoformat(row['created_at'])
            ))
        return addresses

    async def get_all_active_evm_addresses(self) -> List[TrackedAddress]:
        """Get all active EVM addresses across all users."""
        cursor = await self.conn.execute("""
            SELECT * FROM evm_tracked_addresses WHERE active = 1
        """)
        rows = await cursor.fetchall()

        addresses = []
        for row in rows:
            addresses.append(TrackedAddress(
                id=row['id'],
                user_id=row['user_id'],
                address=row['address'],
                label=row['label'],
                address_type=AddressType(row['address_type']),
                token_contract=row['token_contract'],
                token_symbol=row['token_symbol'],
                min_value_usd=row['min_value_usd'],
                active=bool(row['active']),
                created_at=datetime.fromisoformat(row['created_at'])
            ))
        return addresses

    async def get_users_tracking_evm_address(self, address: str) -> List[TrackedAddress]:
        """Get all users tracking a specific EVM address."""
        cursor = await self.conn.execute("""
            SELECT * FROM evm_tracked_addresses WHERE address = ? AND active = 1
        """, (address.lower(),))
        rows = await cursor.fetchall()

        addresses = []
        for row in rows:
            addresses.append(TrackedAddress(
                id=row['id'],
                user_id=row['user_id'],
                address=row['address'],
                label=row['label'],
                address_type=AddressType(row['address_type']),
                token_contract=row['token_contract'],
                token_symbol=row['token_symbol'],
                min_value_usd=row['min_value_usd'],
                active=bool(row['active']),
                created_at=datetime.fromisoformat(row['created_at'])
            ))
        return addresses

    async def update_evm_address_active(self, address_id: int, active: bool) -> bool:
        """Toggle EVM address tracking on/off."""
        try:
            await self.conn.execute("""
                UPDATE evm_tracked_addresses SET active = ? WHERE id = ?
            """, (int(active), address_id))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating EVM address active status: {e}")
            return False

    async def delete_evm_address(self, address_id: int, user_id: int) -> bool:
        """Delete an EVM tracked address (must belong to user)."""
        try:
            cursor = await self.conn.execute("""
                DELETE FROM evm_tracked_addresses WHERE id = ? AND user_id = ?
            """, (address_id, user_id))
            await self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting EVM address: {e}")
            return False

    # Statistics
    async def get_stats(self) -> dict:
        """Get bot statistics."""
        cursor = await self.conn.execute("SELECT COUNT(*) as count FROM users")
        total_users = (await cursor.fetchone())['count']

        cursor = await self.conn.execute("SELECT COUNT(*) as count FROM wallets")
        total_wallets = (await cursor.fetchone())['count']

        cursor = await self.conn.execute("SELECT COUNT(*) as count FROM wallets WHERE active = 1")
        active_wallets = (await cursor.fetchone())['count']

        cursor = await self.conn.execute("SELECT COUNT(*) as count FROM evm_tracked_addresses WHERE active = 1")
        active_evm_addresses = (await cursor.fetchone())['count']

        return {
            'total_users': total_users,
            'total_wallets': total_wallets,
            'active_wallets': active_wallets,
            'active_evm_addresses': active_evm_addresses
        }

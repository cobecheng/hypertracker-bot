#!/usr/bin/env python3
"""
Migration script to enable TWAP notifications for all existing wallets.
Run this once to update existing wallets to have TWAP notifications enabled.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings
from core.database import Database
from core.models import NotificationType


async def migrate():
    """Enable TWAP notifications for all existing wallets."""
    settings = get_settings()
    db = Database(settings.database_path)

    await db.connect()

    try:
        # Get all users first
        all_users = await db.get_all_users()

        # Get all wallets from all users
        all_wallets = []
        for user in all_users:
            user_wallets = await db.get_user_wallets(user.telegram_id)
            all_wallets.extend(user_wallets)

        print(f"Found {len(all_wallets)} wallets across {len(all_users)} users")

        updated_count = 0
        already_enabled_count = 0

        for wallet in all_wallets:
            # Check if TWAP is already enabled
            if NotificationType.TWAP in wallet.filters.notify_on:
                already_enabled_count += 1
                print(f"  ✓ Wallet {wallet.id} ({wallet.alias or wallet.address[:10]}...) - TWAP already enabled")
                continue

            # Add TWAP to notify_on list
            wallet.filters.notify_on.append(NotificationType.TWAP)

            # Update in database
            success = await db.update_wallet_filters(wallet.id, wallet.filters)

            if success:
                updated_count += 1
                print(f"  ✅ Wallet {wallet.id} ({wallet.alias or wallet.address[:10]}...) - TWAP enabled")
            else:
                print(f"  ❌ Wallet {wallet.id} ({wallet.alias or wallet.address[:10]}...) - Failed to update")

        print(f"\nMigration complete!")
        print(f"  Updated: {updated_count} wallets")
        print(f"  Already enabled: {already_enabled_count} wallets")
        print(f"  Total: {len(all_wallets)} wallets")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(migrate())

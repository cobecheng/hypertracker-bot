#!/usr/bin/env python3
"""
Migration script to handle old log files.

This script helps you deal with the old hypertracker.log file (328 MB)
by archiving it before switching to the new logging system.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path


def migrate_old_logs():
    """Archive old log files before switching to new system."""

    old_logs = ["hypertracker.log", "bot.log"]
    archive_dir = Path("logs/archive")
    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for log_file in old_logs:
        if not os.path.exists(log_file):
            continue

        file_size_mb = os.path.getsize(log_file) / (1024 * 1024)

        print(f"\n📄 Found old log file: {log_file} ({file_size_mb:.1f} MB)")

        # Ask user what to do
        print("\nOptions:")
        print("  1. Archive (move to logs/archive/)")
        print("  2. Delete (permanently remove)")
        print("  3. Skip (keep in current location)")

        choice = input(f"\nWhat would you like to do with {log_file}? [1/2/3]: ").strip()

        if choice == "1":
            # Archive the file
            archive_name = f"{Path(log_file).stem}_{timestamp}.log"
            archive_path = archive_dir / archive_name
            shutil.move(log_file, archive_path)
            print(f"✅ Archived to {archive_path}")

        elif choice == "2":
            # Delete the file
            confirm = input(f"⚠️  Are you sure you want to DELETE {log_file}? [yes/no]: ").strip().lower()
            if confirm == "yes":
                os.remove(log_file)
                print(f"🗑️  Deleted {log_file}")
            else:
                print(f"⏭️  Skipped {log_file}")

        else:
            print(f"⏭️  Skipped {log_file}")

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("\nNew logging system will create files in logs/ directory:")
    print("  - logs/system.log (main log)")
    print("  - logs/liquidations.log (liquidation events)")
    print("  - logs/fills.log (trading fills)")
    print("  - logs/errors.log (errors only)")
    print("\nEach file max 50 MB with 5 backups (auto-rotation)")
    print("Logs older than 7 days auto-deleted on startup")
    print("=" * 60)


if __name__ == "__main__":
    print("=" * 60)
    print("HyperTracker Bot - Log Migration Utility")
    print("=" * 60)
    migrate_old_logs()

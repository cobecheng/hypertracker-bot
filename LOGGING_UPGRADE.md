# Logging System Upgrade Guide

## What Changed?

The bot now uses an **advanced multi-file logging system** instead of a single monolithic log file.

### Before (Old System)
- ❌ Single file: `hypertracker.log` (328 MB!)
- ❌ No rotation - grows indefinitely
- ❌ No cleanup - manual deletion required
- ❌ Mixed content - hard to find specific events
- ❌ Performance issues with large files

### After (New System)
- ✅ **Separate log files** by event type
- ✅ **Automatic rotation** at 50 MB per file
- ✅ **Automatic cleanup** of logs older than 7 days
- ✅ **Organized structure** - easy to find events
- ✅ **Maximum disk usage**: ~1 GB total (vs unlimited before)

---

## New Log Files Structure

```
logs/
├── system.log          # Main application log (all events)
├── system.log.1        # Backup 1 (most recent)
├── system.log.2        # Backup 2
├── system.log.3        # Backup 3
├── system.log.4        # Backup 4
├── system.log.5        # Backup 5 (oldest)
│
├── liquidations.log    # Liquidation events only
├── liquidations.log.1
├── liquidations.log.2
├── ...
│
├── fills.log           # Trading fills only
├── fills.log.1
├── fills.log.2
├── ...
│
├── errors.log          # Errors only (high priority)
├── errors.log.1
└── ...
```

---

## Migration Steps

### 1. Handle Old Log Files

Run the migration script to deal with your old 328 MB `hypertracker.log`:

```bash
python3 migrate_old_logs.py
```

**Options:**
- **Archive**: Moves old logs to `logs/archive/hypertracker_YYYYMMDD_HHMMSS.log`
- **Delete**: Permanently removes old logs (frees 328 MB)
- **Skip**: Keeps old logs in place (new logs go to `logs/` directory)

**Recommendation**: Archive if you need historical data, otherwise delete.

### 2. Restart the Bot

```bash
# Stop current bot
pkill -f "python.*run.py"

# Start with new logging system
python run.py
```

### 3. Verify New Logs

Check that new logs are being created:

```bash
ls -lh logs/

# Should show:
# system.log
# liquidations.log
# fills.log
# errors.log
```

---

## How to Use New Logs

### Monitor Live Liquidations
```bash
tail -f logs/liquidations.log
```

**Output format:**
```
2025-12-06 04:39:25 - liquidations - INFO - Binance BTCUSDT long $100,000
2025-12-06 04:39:26 - liquidations - INFO - Bybit ETHUSDT short $75,500
2025-12-06 04:39:27 - liquidations - INFO - Gate.io SOLUSDT long $52,000
```

### Monitor Live Fills (Trading Activity)
```bash
tail -f logs/fills.log
```

**Output format:**
```
2025-12-06 04:39:25 - fills - INFO - 0x1234abcd... BTC B 0.5 @ $95000.00
2025-12-06 04:39:26 - fills - INFO - 0x5678efgh... ETH A 2.0 @ $3500.50
```

### Monitor System Events
```bash
tail -f logs/system.log
```

### Check Errors Only
```bash
tail -f logs/errors.log
```

### Search for Specific Exchange
```bash
grep "Binance" logs/liquidations.log | tail -20
grep "Bybit" logs/liquidations.log | tail -20
grep "Gate.io" logs/liquidations.log | tail -20
```

### Analyze Liquidations by Hour
```bash
# Count liquidations in current hour by venue
grep "$(date '+%Y-%m-%d %H')" logs/liquidations.log | \
  grep -o "Binance\|Bybit\|Gate.io" | sort | uniq -c

# Example output:
#  142 Binance
#   18 Bybit
#    5 Gate.io
```

---

## Automatic Management Features

### 🔄 Log Rotation

**How it works:**
1. When a log file reaches **50 MB**, it stops being written to
2. The file is renamed with a `.1` suffix (e.g., `system.log` → `system.log.1`)
3. Existing backups are shifted (`.1` → `.2`, `.2` → `.3`, etc.)
4. Oldest backup (`.5`) is deleted
5. A new empty log file is created

**Example:**
```
system.log         (48 MB)  → Writing continues
system.log         (50 MB)  → Rotation triggered!
system.log.1       (50 MB)  → Renamed from system.log
system.log         (0 MB)   → New file created
```

**Total space per log type:** 50 MB × 6 files = 300 MB maximum
**Total space all logs:** ~1 GB maximum

### 🧹 Automatic Cleanup

**When it runs:** Every time you start the bot

**What it does:**
- Scans `logs/` directory for all `.log` and `.log.*` files
- Deletes any files older than **7 days**
- Logs how much space was freed

**Example output on startup:**
```
2025-12-06 04:39:25 - root - INFO - Cleaned up 12 old log files (156.45 MB freed)
```

**Manual cleanup (if needed):**
```bash
# Remove logs older than 7 days
find logs/ -name "*.log*" -mtime +7 -delete

# Remove all backups (keep only current logs)
rm logs/*.log.[0-9]
```

---

## Configuration (Advanced)

Edit `utils/logging_config.py` to customize:

### Change Retention Period
```python
LOG_RETENTION_DAYS = 30  # Keep logs for 30 days instead of 7
```

### Change Max File Size
```python
MAX_BYTES = 100 * 1024 * 1024  # 100 MB instead of 50 MB
```

### Change Backup Count
```python
BACKUP_COUNT = 10  # Keep 10 backups instead of 5
```

### Change Log Level
```python
# In main.py
loggers = setup_logging(log_level="DEBUG")  # More verbose
loggers = setup_logging(log_level="WARNING")  # Less verbose
```

---

## Monitoring Commands

### Check Current Disk Usage
```bash
du -h logs/
```

### Get Detailed Usage Statistics
```python
python3 -c "
from utils.logging_config import get_disk_usage
usage = get_disk_usage()
print(f'Total: {usage[\"total_size_mb\"]:.2f} MB')
for file, size in usage['files'].items():
    print(f'  {file}: {size:.2f} MB')
"
```

### Count Total Log Entries
```bash
wc -l logs/*.log
```

### Find Largest Log Files
```bash
ls -lhS logs/
```

---

## Recommended Cleanup Scheme

### For Production (Your Current Setup)
- ✅ **Retention**: 7 days (default)
- ✅ **Max file size**: 50 MB (default)
- ✅ **Backups**: 5 per log type (default)
- ✅ **Total disk**: ~1 GB maximum
- ✅ **Cleanup**: Automatic on startup

**Why this works:**
- 7 days captures a full week of data for analysis
- 50 MB files are small enough for fast searching
- 1 GB total is negligible on modern servers
- Automatic cleanup prevents disk space issues

### For High-Volume Scenarios
If you're tracking 100+ wallets or getting 1000+ liquidations/day:

```python
# In utils/logging_config.py
LOG_RETENTION_DAYS = 3      # Keep only 3 days
MAX_BYTES = 100 * 1024 * 1024  # 100 MB per file
BACKUP_COUNT = 3            # Only 3 backups
```

**Result:** ~1.2 GB total, 3-day retention

### For Debugging/Development
If you need more verbose logging temporarily:

```python
# In main.py
loggers = setup_logging(log_level="DEBUG")
```

Then change back to `INFO` when done.

---

## Troubleshooting

### Logs Not Appearing?
Check that the `logs/` directory was created:
```bash
ls -la logs/
```

If missing, the logging system will create it on startup.

### Old hypertracker.log Still Growing?
Make sure you restarted the bot after the upgrade:
```bash
pkill -f "python.*run.py"
python run.py
```

### Want to Archive Old Logs?
```bash
python3 migrate_old_logs.py
```

### Disk Space Still an Issue?
1. Reduce retention: `LOG_RETENTION_DAYS = 3`
2. Reduce backups: `BACKUP_COUNT = 2`
3. Manually delete old archives:
   ```bash
   rm -rf logs/archive/
   ```

---

## Benefits Summary

| Feature | Old System | New System |
|---------|-----------|------------|
| **Max disk usage** | Unlimited (328 MB+) | ~1 GB |
| **Rotation** | Manual | Automatic |
| **Cleanup** | Manual | Automatic (7 days) |
| **Find liquidations** | Grep 328 MB file | Cat dedicated file |
| **Find errors** | Grep 328 MB file | Cat errors.log only |
| **Performance** | Slow (large file) | Fast (small files) |
| **Maintenance** | Manual deletion | Zero maintenance |

---

## Questions?

Check the detailed documentation:
- [logs/README.md](logs/README.md) - Detailed log file reference
- [utils/logging_config.py](utils/logging_config.py) - Configuration options

For issues, check `logs/errors.log` first!

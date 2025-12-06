# Liquidation Statistics Feature

## Overview

The bot now tracks hourly liquidation statistics for all three venues (Binance, Bybit, Gate.io) and displays them in an easy-to-read format.

## How It Works

### Tracking
- **Total liquidations**: All liquidations received from WebSocket feeds (including filtered ones)
- **Sent notifications**: Liquidations that passed your filters and were sent to you
- **Filtered out**: Liquidations that didn't meet your criteria (wrong venue, pair, or below min notional)

### Automatic Reset
- Statistics reset **hourly per venue**
- Each venue tracks independently (Binance resets at different times than Bybit, etc.)
- Reset happens exactly 60 minutes after the last reset time

## Accessing Statistics

### Via Bot Menu
1. Open bot menu: `/menu`
2. Click **"💥 Liquidations"**
3. Click **"📊 Hourly Statistics"**

### What You'll See

```
📊 Liquidation Statistics (Last Hour)

Binance
├ Total received: 142
├ Sent to you: 8 (5.6%)
└ Filtered out: 134

Bybit
├ Total received: 18
├ Sent to you: 2 (11.1%)
└ Filtered out: 16

Gate.io
├ Total received: 5
├ Sent to you: 0 (0.0%)
└ Filtered out: 5

Summary
├ Total across all venues: 165
├ Notifications sent: 10
└ Filtered out: 155

Stats reset hourly per venue
Filtered = below your min notional or wrong venue/pair
```

## Understanding the Numbers

### Total Received
- Raw count of all liquidations from the exchange WebSocket
- Includes everything: large, small, all pairs, all directions
- **Not affected by your filters**

### Sent to You
- Liquidations that passed all your filters:
  - ✅ Venue enabled in your settings
  - ✅ Pair matches (if you have pair filter)
  - ✅ Above your min notional threshold
- These are the notifications you actually received in Telegram

### Filtered Out
- Liquidations that were blocked by your filters
- `Filtered Out = Total Received - Sent to You`

### Percentage
- Shows what % of total liquidations you received
- Lower % = stricter filters
- Higher % = more inclusive filters

## Example Scenarios

### Scenario 1: High Filter Rate
```
Binance
├ Total received: 200
├ Sent to you: 5 (2.5%)
└ Filtered out: 195
```
**Reason**: You have a high min notional (e.g., $100,000+) so most liquidations are filtered out.

### Scenario 2: Low Filter Rate
```
Binance
├ Total received: 200
├ Sent to you: 180 (90.0%)
└ Filtered out: 20
```
**Reason**: You have a low min notional (e.g., $10,000) and monitor all pairs, so most liquidations pass.

### Scenario 3: Venue Disabled
```
Gate.io
├ Total received: 25
├ Sent to you: 0 (0.0%)
└ Filtered out: 25
```
**Reason**: You disabled Gate.io in your venue settings, so all liquidations are filtered.

## Use Cases

### 1. Optimize Your Filters
- If **sent % is too low** (< 1%): Consider lowering your min notional threshold
- If **sent % is too high** (> 50%): Consider raising your min notional to reduce noise
- If **one venue shows 0%**: Check if that venue is enabled in your settings

### 2. Monitor Market Activity
- **High total counts** = Volatile market conditions
- **Low total counts** = Quiet/stable market
- Compare venues to see which has most liquidation activity

### 3. Troubleshooting
- **Not receiving notifications?**
  - Check if "Sent to you" is 0 for all venues
  - If so, your filters are too strict or venues are disabled
- **Too many notifications?**
  - Check "Sent to you" percentage
  - Increase min notional to reduce count

## Technical Details

### Statistics Storage
- Stored in memory (resets when bot restarts)
- Each venue tracks independently:
  ```python
  {
      'Binance': {'total': 0, 'sent': 0, 'last_reset': datetime},
      'Bybit': {'total': 0, 'sent': 0, 'last_reset': datetime},
      'Gate.io': {'total': 0, 'sent': 0, 'last_reset': datetime},
  }
  ```

### Hourly Reset Logic
```python
# Check if more than 1 hour (3600 seconds) has passed
if (now - last_reset).total_seconds() > 3600:
    total = 0
    sent = 0
    last_reset = now
```

### Counting Logic
1. **Every liquidation received** → Increment `total`
2. **Check user filters** → If passes, send notification
3. **If notification sent** → Increment `sent`
4. **Never sent** → Increment `total` only (counted as filtered)

## Logs

Statistics are also logged to `logs/liquidations.log`:
```bash
# View recent liquidations
tail -f logs/liquidations.log

# Count by venue in last hour
grep "$(date '+%Y-%m-%d %H')" logs/liquidations.log | \
  grep -o "Binance\|Bybit\|Gate.io" | sort | uniq -c
```

## FAQ

**Q: Why do stats reset hourly instead of daily?**
A: Hourly resets provide more granular insights into market conditions. You can see volatility spikes in real-time.

**Q: What happens if the bot restarts?**
A: Statistics reset to 0 for all venues. They're stored in memory, not database.

**Q: Can I see historical statistics?**
A: Not currently. Only the last hour is tracked. Use `logs/liquidations.log` for historical data.

**Q: Why does Gate.io show lower numbers?**
A: Gate.io has less market share than Binance/Bybit, so naturally fewer liquidations occur there.

**Q: What if I change my filters mid-hour?**
A: The statistics continue tracking with the new filters. "Sent to you" count reflects whatever filters were active when each liquidation occurred.

## Related Settings

- **Min Notional**: `/menu` → Liquidations → Min Notional USD
- **Venue Selection**: `/menu` → Liquidations → Select Venues
- **Pair Filtering**: `/menu` → Liquidations → Filter Pairs

## Future Enhancements

Potential improvements (not yet implemented):
- 24-hour rolling statistics
- Peak liquidation times tracking
- Average liquidation size per venue
- Export statistics to CSV
- Persistence across bot restarts

"""
Open Interest (OI) Monitor (Future Feature)

This module will monitor open interest buildup and changes across
perpetual futures markets.

Planned features:
- Track OI changes for major pairs (BTC, ETH, SOL, etc.)
- Alert on rapid OI buildup (potential for large moves)
- Monitor OI delta vs price action
- Cross-venue OI aggregation
- Historical OI trend analysis

Implementation notes:
- Use exchange APIs for OI data (Binance, Bybit, OKX, Hyperliquid)
- Calculate OI change rate and absolute changes
- Set thresholds for significant OI events
- Correlate with funding rates for better signals
"""
import logging

logger = logging.getLogger(__name__)


class OpenInterestMonitor:
    """Monitor open interest buildup and changes (to be implemented)."""
    
    def __init__(self):
        logger.info("OpenInterestMonitor initialized (placeholder)")
    
    async def start(self):
        """Start monitoring open interest."""
        logger.info("OI monitoring not yet implemented")
    
    async def stop(self):
        """Stop monitoring."""
        pass

"""
Advanced logging configuration for HyperTracker Bot.

Features:
- Separate log files for different event types (liquidations, fills, system)
- Rotating file handlers (max 50MB per file, keep 5 backups)
- Automatic cleanup of old logs (keeps last 7 days)
- Console output for real-time monitoring
- Structured logging with proper formatting
"""
import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime, timedelta
import glob


# Log directory structure
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Separate log files for different purposes
SYSTEM_LOG = LOG_DIR / "system.log"
LIQUIDATIONS_LOG = LOG_DIR / "liquidations.log"
FILLS_LOG = LOG_DIR / "fills.log"
ERRORS_LOG = LOG_DIR / "errors.log"

# Rotation settings
MAX_BYTES = 50 * 1024 * 1024  # 50 MB per file
BACKUP_COUNT = 5  # Keep 5 backup files (total ~250 MB per log type)

# Cleanup settings
LOG_RETENTION_DAYS = 7  # Keep logs for 7 days


def setup_logging(log_level: str = "INFO") -> dict:
    """
    Configure advanced logging system with rotation and cleanup.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        dict: Dictionary of specialized loggers
    """
    # Convert log level string to logging constant
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Common formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler (for real-time monitoring)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # ===== SYSTEM LOG =====
    # Main application log with rotation
    system_handler = logging.handlers.RotatingFileHandler(
        SYSTEM_LOG,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    system_handler.setLevel(level)
    system_handler.setFormatter(formatter)

    # ===== LIQUIDATIONS LOG =====
    # Separate file for all liquidation events
    liquidations_handler = logging.handlers.RotatingFileHandler(
        LIQUIDATIONS_LOG,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    liquidations_handler.setLevel(logging.INFO)
    liquidations_handler.setFormatter(formatter)

    # ===== FILLS LOG =====
    # Separate file for trading fills/orders
    fills_handler = logging.handlers.RotatingFileHandler(
        FILLS_LOG,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    fills_handler.setLevel(logging.INFO)
    fills_handler.setFormatter(formatter)

    # ===== ERRORS LOG =====
    # Critical errors only (easier to monitor)
    errors_handler = logging.handlers.RotatingFileHandler(
        ERRORS_LOG,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(formatter)

    # Configure root logger (catches all logs)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()  # Remove any existing handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(system_handler)
    root_logger.addHandler(errors_handler)

    # Create specialized loggers
    liquidations_logger = logging.getLogger('liquidations')
    liquidations_logger.addHandler(liquidations_handler)
    liquidations_logger.propagate = True  # Also log to root (console + system)

    fills_logger = logging.getLogger('fills')
    fills_logger.addHandler(fills_handler)
    fills_logger.propagate = True

    # Clean up old logs on startup
    cleanup_old_logs()

    # Log startup info
    root_logger.info("=" * 80)
    root_logger.info("HyperTracker Bot logging system initialized")
    root_logger.info(f"Log directory: {LOG_DIR.absolute()}")
    root_logger.info(f"Log level: {log_level}")
    root_logger.info(f"Rotation: {MAX_BYTES // (1024*1024)} MB per file, {BACKUP_COUNT} backups")
    root_logger.info(f"Retention: {LOG_RETENTION_DAYS} days")
    root_logger.info("=" * 80)

    return {
        'system': root_logger,
        'liquidations': liquidations_logger,
        'fills': fills_logger,
    }


def cleanup_old_logs():
    """
    Delete log files older than LOG_RETENTION_DAYS.

    Runs automatically on startup to prevent disk space issues.
    Keeps backup files (.1, .2, etc.) for current logs.
    """
    cutoff_time = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    deleted_count = 0
    total_size_freed = 0

    # Find all .log files and their backups in the log directory
    log_patterns = [
        LOG_DIR / "*.log",
        LOG_DIR / "*.log.*",  # Backup files (.log.1, .log.2, etc.)
    ]

    for pattern in log_patterns:
        for log_file in glob.glob(str(pattern)):
            log_path = Path(log_file)

            # Skip if file doesn't exist (race condition)
            if not log_path.exists():
                continue

            # Get file modification time
            try:
                mtime = datetime.fromtimestamp(log_path.stat().st_mtime)

                # Delete if older than retention period
                if mtime < cutoff_time:
                    file_size = log_path.stat().st_size
                    log_path.unlink()
                    deleted_count += 1
                    total_size_freed += file_size
            except Exception as e:
                # Log error but continue cleanup
                logging.error(f"Error cleaning up {log_path}: {e}")

    if deleted_count > 0:
        size_mb = total_size_freed / (1024 * 1024)
        logging.info(f"Cleaned up {deleted_count} old log files ({size_mb:.2f} MB freed)")


def get_disk_usage() -> dict:
    """
    Get current disk usage statistics for log directory.

    Returns:
        dict: {
            'total_size_mb': float,
            'file_count': int,
            'files': {filename: size_mb}
        }
    """
    total_size = 0
    file_info = {}

    for log_file in glob.glob(str(LOG_DIR / "*")):
        log_path = Path(log_file)
        if log_path.is_file():
            size = log_path.stat().st_size
            total_size += size
            file_info[log_path.name] = size / (1024 * 1024)

    return {
        'total_size_mb': total_size / (1024 * 1024),
        'file_count': len(file_info),
        'files': file_info
    }


# Convenience functions for common logging patterns

def log_liquidation(venue: str, pair: str, notional_usd: float, direction: str = ""):
    """Log liquidation event to dedicated liquidation log."""
    logger = logging.getLogger('liquidations')
    direction_str = f" {direction}" if direction else ""
    logger.info(f"{venue} {pair}{direction_str} ${notional_usd:,.0f}")


def log_fill(wallet: str, coin: str, side: str, size: float, price: float, notional: float):
    """Log fill event to dedicated fills log."""
    logger = logging.getLogger('fills')
    logger.info(f"{wallet[:10]}... {coin} {side} {size} @ ${price:.2f} (${notional:,.0f})")


def log_system(message: str, level: str = "INFO"):
    """Log system event."""
    logger = logging.getLogger()
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message)

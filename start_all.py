#!/usr/bin/env python3
"""
Master process manager for HyperTracker Bot.
Runs both the Telegram bot and Alchemy webhook server together.

Usage:
    python start_all.py

This will start:
1. Main bot (run.py) - Handles Telegram interactions and Hyperliquid tracking
2. Alchemy webhook server - Handles EVM transaction webhooks on port 8080

Press Ctrl+C to stop both processes.
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProcessManager:
    """Manages multiple async processes."""

    def __init__(self):
        self.processes = []
        self.tasks = []
        self.shutdown_event = asyncio.Event()

    async def run_bot(self):
        """Run the main Telegram bot."""
        logger.info("🤖 Starting HyperTracker Bot...")
        try:
            # Import and run the main bot
            from main import HyperTrackerBot

            bot = HyperTrackerBot()
            await bot.setup()
            await bot.start()

        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}", exc_info=True)
            self.shutdown_event.set()

    async def run_webhook_server(self):
        """Run the Alchemy webhook server."""
        logger.info("🔷 Starting Alchemy Webhook Server...")
        try:
            import uvicorn
            from alchemy_webhook_server import app

            config = uvicorn.Config(
                app=app,
                host="0.0.0.0",
                port=8080,
                log_level="info",
                access_log=True
            )
            server = uvicorn.Server(config)
            await server.serve()

        except Exception as e:
            logger.error(f"❌ Webhook server crashed: {e}", exc_info=True)
            self.shutdown_event.set()

    async def monitor_shutdown(self):
        """Monitor for shutdown signal."""
        await self.shutdown_event.wait()
        logger.info("🛑 Shutdown signal received, stopping all processes...")

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("✅ All processes stopped")

    async def start(self):
        """Start all processes."""
        logger.info("=" * 80)
        logger.info("🚀 HyperTracker Bot - Starting All Services")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Services:")
        logger.info("  1. Telegram Bot (Hyperliquid tracking + commands)")
        logger.info("  2. Webhook Server (EVM tracking - port 8080)")
        logger.info("")
        logger.info("Press Ctrl+C to stop all services")
        logger.info("=" * 80)
        logger.info("")

        # Create tasks
        self.tasks = [
            asyncio.create_task(self.run_bot(), name="telegram_bot"),
            asyncio.create_task(self.run_webhook_server(), name="webhook_server"),
            asyncio.create_task(self.monitor_shutdown(), name="shutdown_monitor")
        ]

        # Wait for all tasks
        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("Tasks cancelled")

    def handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        self.shutdown_event.set()


async def main():
    """Main entry point."""
    manager = ProcessManager()

    # Setup signal handlers
    signal.signal(signal.SIGINT, manager.handle_signal)
    signal.signal(signal.SIGTERM, manager.handle_signal)

    try:
        await manager.start()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
        manager.shutdown_event.set()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")
        sys.exit(0)

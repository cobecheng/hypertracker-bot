"""
Standalone webhook server for receiving Alchemy events.
Runs alongside the main bot to handle HTTP webhooks.

Usage:
    python alchemy_webhook_server.py

Or with uvicorn:
    uvicorn alchemy_webhook_server:app --host 0.0.0.0 --port 8080
"""
import asyncio
import logging
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("FastAPI not installed. Install with: pip install fastapi uvicorn")
    exit(1)

from config import get_settings, ensure_data_directory
from core.database import Database
from bot.notifier import Notifier
from aiogram import Bot
from bot.handlers import alchemy_webhook

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG to see detailed logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global instances
db: Database = None
notifier: Notifier = None
bot: Bot = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app."""
    global db, notifier, bot

    logger.info("Starting Alchemy webhook server...")
    settings = get_settings()

    # Ensure data directory exists
    ensure_data_directory()

    # Initialize database
    db = Database(settings.database_path)
    await db.connect()
    logger.info("Database connected")

    # Initialize bot and notifier
    bot = Bot(token=settings.bot_token)
    notifier = Notifier(bot)
    logger.info("Bot and notifier initialized")

    # Set global references for webhook handler
    alchemy_webhook.db = db
    alchemy_webhook.notifier = notifier

    logger.info("✅ Webhook server ready to receive Alchemy events")

    yield

    # Cleanup
    logger.info("Shutting down webhook server...")
    await db.close()
    await bot.session.close()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="HyperTracker Alchemy Webhook Server",
    description="Receives and processes Alchemy webhook events for EVM tracking",
    version="1.0.0",
    lifespan=lifespan
)


# Include webhook router
app.include_router(alchemy_webhook.fastapi_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "HyperTracker Alchemy Webhook Server",
        "endpoints": {
            "webhook": "/alchemy-webhook",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "connected" if db and db.conn else "disconnected",
        "notifier": "ready" if notifier else "not initialized"
    }


if __name__ == "__main__":
    settings = get_settings()

    # Run server
    logger.info("Starting webhook server on 0.0.0.0:8080")
    logger.info("Webhook URL: http://YOUR_SERVER_IP:8080/alchemy-webhook")
    logger.info("For local testing with ngrok: ngrok http 8080")

    uvicorn.run(
        "alchemy_webhook_server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )

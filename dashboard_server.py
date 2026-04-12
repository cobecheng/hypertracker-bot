"""
Local dashboard server for HyperTracker analytics.

Usage:
    python dashboard_server.py
"""
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from config import ensure_data_directory, get_settings
from core.database import Database
from core.hyperliquid_info_client import HyperliquidInfoClient


PROJECT_ROOT = Path(__file__).parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"

db: Database | None = None
info_client: HyperliquidInfoClient | None = None
live_poll_task: asyncio.Task | None = None


def get_window_start_ms(window: str) -> int:
    """Convert a dashboard window string into a UTC start timestamp."""
    mapping = {
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    if window not in mapping:
        raise HTTPException(status_code=400, detail="Unsupported window")

    now = datetime.now(timezone.utc)
    return int((now - mapping[window]).timestamp() * 1000)


def parse_live_positions(snapshot: dict) -> tuple[list[dict], float, float, float, float]:
    """Normalize Hyperliquid clearinghouse state into dashboard-friendly positions."""
    margin_summary = snapshot.get("marginSummary", {}) or {}
    account_value = float(margin_summary.get("accountValue", 0) or 0)
    total_margin_used = float(margin_summary.get("totalMarginUsed", 0) or 0)
    withdrawable = float(snapshot.get("withdrawable", 0) or 0)

    positions = []
    for item in snapshot.get("assetPositions", []) or []:
        position = item.get("position", {}) or {}
        size = float(position.get("szi", 0) or 0)
        if size == 0:
            continue

        coin = position.get("coin") or "UNKNOWN"
        entry_px = float(position.get("entryPx", 0) or 0)
        notional = abs(float(position.get("positionValue", 0) or 0))
        unrealized = float(position.get("unrealizedPnl", 0) or 0)
        leverage_value = (position.get("leverage") or {}).get("value")
        liquidation_px = float(position.get("liquidationPx", 0) or 0)

        positions.append({
            "coin": coin,
            "direction": "long" if size > 0 else "short",
            "size": abs(size),
            "signed_size": size,
            "entry_px": entry_px,
            "position_notional_usd": notional,
            "unrealized_pnl_usd": unrealized,
            "leverage": float(leverage_value or 0),
            "liquidation_px": liquidation_px,
        })

    total_notional = sum(position["position_notional_usd"] for position in positions)
    positions.sort(key=lambda item: item["position_notional_usd"], reverse=True)
    return positions, account_value, total_notional, withdrawable if withdrawable else 0.0, total_margin_used


def merge_live_snapshots(snapshots: list[tuple[str, dict]]) -> tuple[list[dict], int, float, float, float, float, dict]:
    """Merge default and HIP-3 perp dex snapshots into one combined wallet view."""
    merged_positions: list[dict] = []
    latest_snapshot_time_ms = 0
    total_account_value = 0.0
    total_notional_usd = 0.0
    total_withdrawable = 0.0
    total_margin_used = 0.0
    raw_snapshots: dict[str, dict] = {}

    for dex, snapshot in snapshots:
        positions, account_value, notional_usd, withdrawable, margin_used = parse_live_positions(snapshot)
        for position in positions:
            position["dex"] = dex or "default"
        merged_positions.extend(positions)
        total_account_value += account_value
        total_notional_usd += notional_usd
        total_withdrawable += withdrawable
        total_margin_used += margin_used
        latest_snapshot_time_ms = max(latest_snapshot_time_ms, int(snapshot.get("time") or 0))
        raw_snapshots[dex or "default"] = snapshot

    merged_positions.sort(key=lambda item: item["position_notional_usd"], reverse=True)
    return (
        merged_positions,
        latest_snapshot_time_ms,
        total_account_value,
        total_notional_usd,
        total_withdrawable,
        total_margin_used,
        raw_snapshots,
    )


async def poll_live_snapshots():
    """Poll Hyperliquid live account state and cache it locally."""
    settings = get_settings()
    interval = max(15, settings.dashboard_live_poll_interval_seconds)

    await asyncio.sleep(2)
    while True:
        try:
            active_wallets = await db.get_all_active_wallets()
            for wallet in active_wallets:
                try:
                    dexes = await db.get_wallet_live_dexes(wallet.id)
                    snapshots: list[tuple[str, dict]] = [("", await info_client.fetch_clearinghouse_state(wallet.address))]
                    for dex in dexes:
                        snapshots.append((dex, await info_client.fetch_clearinghouse_state(wallet.address, dex=dex)))

                    (
                        positions,
                        snapshot_time_ms,
                        account_value,
                        total_notional,
                        withdrawable,
                        total_margin_used,
                        raw_snapshot,
                    ) = merge_live_snapshots(snapshots)
                    if not snapshot_time_ms:
                        snapshot_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    await db.upsert_wallet_live_snapshot(
                        wallet=wallet,
                        snapshot_time_ms=snapshot_time_ms,
                        positions=positions,
                        raw_snapshot=raw_snapshot,
                        account_value=account_value,
                        total_notional_usd=total_notional,
                        total_margin_used=total_margin_used,
                        withdrawable=withdrawable,
                    )
                except Exception as wallet_error:
                    print(f"Live snapshot poll failed for {wallet.address}: {wallet_error}")
                await asyncio.sleep(0.35)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"Live snapshot poll loop error: {error}")

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared resources for the dashboard app."""
    global db, info_client, live_poll_task

    settings = get_settings()
    ensure_data_directory()

    db = Database(settings.database_path)
    await db.connect()
    info_client = HyperliquidInfoClient(settings.hyperliquid_rest_url)
    live_poll_task = asyncio.create_task(poll_live_snapshots())
    try:
        yield
    finally:
        if live_poll_task:
            live_poll_task.cancel()
            try:
                await live_poll_task
            except asyncio.CancelledError:
                pass
        if info_client:
            await info_client.close()
        await db.close()


app = FastAPI(
    title="HyperTracker Dashboard",
    description="Local analytics dashboard for tracked Hyperliquid wallets",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/dashboard/static", StaticFiles(directory=DASHBOARD_DIR), name="dashboard-static")


@app.get("/")
async def root():
    """Redirect to the dashboard UI."""
    return RedirectResponse(url="/dashboard", status_code=307)


@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok", "database": bool(db and db.conn)}


@app.get("/dashboard")
async def dashboard_index():
    """Serve the local dashboard UI."""
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/api/dashboard/overview")
async def dashboard_overview(window: str = Query(default="1h")):
    start_ms = get_window_start_ms(window)
    return await db.get_dashboard_overview(start_ms)


@app.get("/api/dashboard/assets")
async def dashboard_assets(
    window: str = Query(default="1h"),
    limit: int = Query(default=25, ge=1, le=100),
):
    start_ms = get_window_start_ms(window)
    return {"items": await db.get_dashboard_asset_flows(start_ms, limit)}


@app.get("/api/dashboard/live-overview")
async def dashboard_live_overview():
    return await db.get_live_dashboard_overview()


@app.get("/api/dashboard/live-assets")
async def dashboard_live_assets(limit: int = Query(default=25, ge=1, le=100)):
    return {"items": await db.get_live_asset_exposure(limit)}


@app.get("/api/dashboard/wallets")
async def dashboard_wallets(
    window: str = Query(default="1h"),
    limit: int = Query(default=100, ge=1, le=300),
):
    start_ms = get_window_start_ms(window)
    return {"items": await db.get_dashboard_wallet_summaries(start_ms, limit)}


@app.get("/api/dashboard/recent-fills")
async def dashboard_recent_fills(
    window: str = Query(default="1h"),
    limit: int = Query(default=50, ge=1, le=200),
):
    start_ms = get_window_start_ms(window)
    return {"items": await db.get_recent_fill_events(start_ms, limit)}


@app.get("/api/dashboard/wallets/{wallet_id}")
async def dashboard_wallet_detail(wallet_id: int, window: str = Query(default="1h")):
    start_ms = get_window_start_ms(window)
    detail = await db.get_wallet_dashboard_detail(wallet_id, start_ms)
    if detail is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return detail


if __name__ == "__main__":
    uvicorn.run(
        "dashboard_server:app",
        host="127.0.0.1",
        port=8090,
        reload=False,
        log_level="info",
    )

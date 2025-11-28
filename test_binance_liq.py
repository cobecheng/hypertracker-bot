"""
Test script to verify Binance liquidation WebSocket feed.
Run this to see live liquidation data from Binance.
"""
import asyncio
import json
import websockets
from datetime import datetime


async def test_binance_liquidations():
    """Connect to Binance liquidation feed and print events."""
    url = "wss://fstream.binance.com/ws/!forceOrder@arr"

    print(f"Connecting to Binance liquidation feed...")
    print(f"URL: {url}\n")

    try:
        async with websockets.connect(url) as ws:
            print("✅ Connected! Listening for liquidations...\n")

            count = 0
            async for message in ws:
                try:
                    data = json.loads(message)
                    count += 1

                    # Binance sends liquidation data in this format
                    if "o" in data:  # Order data
                        order = data["o"]
                        symbol = order.get("s", "")
                        side = order.get("S", "")  # BUY or SELL
                        quantity = order.get("q", "")
                        price = order.get("p", "")

                        # Calculate notional value
                        try:
                            notional = float(quantity) * float(price)
                        except:
                            notional = 0

                        timestamp = datetime.fromtimestamp(data["E"] / 1000)

                        print(f"[{count}] {timestamp.strftime('%H:%M:%S')}")
                        print(f"    {symbol} - {side}")
                        print(f"    Quantity: {quantity}")
                        print(f"    Price: ${price}")
                        print(f"    Notional: ${notional:,.2f}")
                        print()

                        # Stop after 10 liquidations for testing
                        if count >= 10:
                            print("✅ Test complete! Received 10 liquidation events.")
                            break

                except json.JSONDecodeError:
                    print(f"Failed to decode: {message}")
                except Exception as e:
                    print(f"Error: {e}")

    except Exception as e:
        print(f"❌ Connection error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Binance Liquidation Feed Test")
    print("=" * 60)
    print()

    asyncio.run(test_binance_liquidations())

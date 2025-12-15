# EVM Tracking Setup Guide

This guide will help you set up Ethereum (EVM) contract tracking using Alchemy webhooks.

## 🎯 Overview

The EVM tracking system allows you to monitor:
- **Token transfers** (LIT or any ERC-20 token)
- **Treasury wallet activity** (where tokens are held)
- **Deployer actions** (contract creator movements)
- **Custom addresses** (whales, known wallets, etc.)

Notifications are sent to your configured "CA Tracking" Telegram channel.

---

## 📋 Prerequisites

1. **Alchemy Account** (free tier is sufficient)
   - Sign up at: https://www.alchemy.com/
   - Create a new app for Ethereum Mainnet

2. **Server with Public IP** (for webhooks)
   - VPS, Railway.app, Render.com, or similar
   - OR use ngrok for local testing

3. **Telegram Channel/Group** (for notifications)
   - Create a new topic called "CA Tracking" (optional)

---

## 🚀 Step-by-Step Setup

### Step 1: Install Dependencies

```bash
# Activate your virtual environment
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install new dependencies
pip install -r requirements.txt
```

### Step 2: Configure Alchemy

1. **Go to Alchemy Dashboard**: https://dashboard.alchemy.com/

2. **Create a New App**:
   - Click "Create App"
   - Name: "HyperTracker EVM"
   - Chain: Ethereum
   - Network: Ethereum Mainnet
   - Click "Create App"

3. **Get Your API Key**:
   - Click on your app
   - Click "API KEY" button
   - Copy the API key

4. **Create Address Activity Webhook**:
   - Go to "Notify" tab in left sidebar
   - Click "Create Webhook"
   - Select "Address Activity"
   - Select network: "Ethereum Mainnet"

5. **Configure Webhook URL**:
   - If using ngrok (local testing):
     ```bash
     ngrok http 8080
     ```
     Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)
     Webhook URL: `https://abc123.ngrok.io/alchemy-webhook`

   - If using deployed server:
     Webhook URL: `https://your-server.com/alchemy-webhook`

6. **Add Addresses to Monitor**:
   - Add these LIT token addresses:
     - `0x232CE3bd40fCd6f80f3d55A522d03f25Df784Ee2` (LIT Token)
     - `0x077842A5670CB4C83dca62bDA4c36592a5B31891` (LIT Treasury)
     - `0x004Fe354757574E2DEB35fDb304383366f313099` (LIT Deployer)

7. **Test Webhook**:
   - Click "Test Webhook" to verify connection
   - Should see "200 OK" response

8. **Get Signing Key**:
   - After creating webhook, click on it
   - Copy the "Signing Key" (for security verification)
   - Click "Create Webhook" to save

### Step 3: Configure Environment Variables

Edit your `.env` file and add:

```bash
# EVM Tracking (Alchemy)
ALCHEMY_API_KEY=your_alchemy_api_key_here
ALCHEMY_SIGNING_KEY=your_webhook_signing_key_here
ALCHEMY_NETWORK=eth-mainnet

# CA Tracking Notifications
# For private chat (no channel):
CA_TRACKING_CHAT_ID=

# For Telegram group:
CA_TRACKING_CHAT_ID=-1001234567890

# For Telegram group with topic:
CA_TRACKING_CHAT_ID=-1001234567890:12345
```

**How to get CA_TRACKING_CHAT_ID:**
1. Add your bot to the Telegram group
2. Send a message in the group
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for `"chat":{"id":-1001234567890,...}`
5. For topics, the thread_id is in `"message_thread_id":12345`

### Step 4: Run the Services

You need to run **TWO processes**:

#### Terminal 1: Main Bot (Hyperliquid tracking)
```bash
python run.py
```

#### Terminal 2: Webhook Server (Alchemy events)
```bash
python alchemy_webhook_server.py
```

Or using uvicorn:
```bash
uvicorn alchemy_webhook_server:app --host 0.0.0.0 --port 8080
```

**Production deployment (using pm2):**
```bash
# Install pm2 if not already installed
npm install -g pm2

# Start both processes
pm2 start run.py --name hypertracker-bot --interpreter python3
pm2 start alchemy_webhook_server.py --name alchemy-webhook --interpreter python3

# Save process list
pm2 save

# View logs
pm2 logs hypertracker-bot
pm2 logs alchemy-webhook
```

---

## 📱 Using the Bot

### Track LIT Token (Quick Start)

```
/track_lit
```

This automatically adds all three addresses:
- LIT Token Contract
- LIT Treasury (Safe Multisig)
- LIT Deployer

### Track Custom Address

```
/add_evm_address
```

Follow the prompts to add any Ethereum address.

### List Tracked Addresses

```
/list_evm
```

Shows all addresses you're currently tracking.

### Stop Tracking

```
/stop_evm_tracking
```

Shows buttons to stop tracking specific addresses.

### Help

```
/evm_help
```

Shows EVM tracking commands and usage.

---

## 🔔 What Notifications You'll Get

### Treasury Movements (HIGH PRIORITY)
```
🚀 LIT LIQUIDITY PROVISION (Launch Signal!)

💰 Amount: 500,000 LIT ($125,000)
📤 From: 🔐 LIT Treasury
       0x077842...5B31891
📥 To: 🦄 Uniswap V2 Router
       0x7a2507...27b25eff

🔗 Tx: https://etherscan.io/tx/0x1234...5678
⏰ 2025-12-13 15:30:45 UTC
```

### Large Transfers
```
📦 LIT TOKEN TRANSFER

💰 Amount: 100,000 LIT ($25,000)
📤 From: 0x1234...5678
📥 To: 🏦 Binance Hot Wallet
       0x28c6c0...43bf21d60

🔗 Tx: https://etherscan.io/tx/0xabcd...ef12
⏰ 2025-12-13 16:45:22 UTC
```

### Deployer Activity
```
🔔 LIT Deployer Activity

💼 Action: 🏗️ Contract Deployment
📍 To: New Contract Created
💵 Value: 0.5 ETH ($1,200)
⛽ Gas: 85.3 gwei

🔗 Tx: https://etherscan.io/tx/0x9876...4321
⏰ 2025-12-13 17:20:10 UTC
```

---

## 🔧 Troubleshooting

### Webhook Not Receiving Events

1. **Check webhook server is running**:
   ```bash
   curl http://localhost:8080/health
   ```
   Should return: `{"status":"healthy",...}`

2. **Check ngrok tunnel** (if using ngrok):
   ```bash
   curl https://your-ngrok-url.ngrok.io/health
   ```

3. **Verify Alchemy webhook status**:
   - Go to Alchemy dashboard → Notify tab
   - Check webhook status (should be green/active)
   - Click webhook → View Recent Deliveries

4. **Check logs**:
   ```bash
   # Webhook server logs
   tail -f hypertracker.log | grep -i alchemy

   # Or pm2 logs
   pm2 logs alchemy-webhook
   ```

### Database Errors

If you see database errors after updating:

```bash
# Backup current database
cp data/hypertracker.db data/hypertracker.db.backup

# The new table will be created automatically on first run
python run.py
```

### Signature Verification Fails

If you see "Invalid Alchemy webhook signature":

1. Make sure `ALCHEMY_SIGNING_KEY` in `.env` matches the key from Alchemy dashboard
2. The signing key is found in Alchemy dashboard → Notify → Click on your webhook
3. Copy the "Signing Key" exactly (no spaces)

---

## 📊 Testing the Setup

### Test 1: Health Check
```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "notifier": "ready"
}
```

### Test 2: Track LIT Token
1. Send `/track_lit` to your bot
2. Should receive confirmation message
3. Check database:
   ```bash
   sqlite3 data/hypertracker.db "SELECT * FROM evm_tracked_addresses;"
   ```

### Test 3: Wait for Real Events
- LIT token is pre-launch, so no events yet
- When treasury makes first transfer, you'll get instant notification
- For testing, you can add a high-volume token like USDT:
  - `/add_evm_address`
  - Enter: `0xdac17f958d2ee523a2206206994597c13d831ec7`
  - Label: "USDT Test"

---

## 💰 Cost Breakdown

| Service | Monthly Cost | Notes |
|---------|--------------|-------|
| **Alchemy Free Tier** | $0 | 300M compute units/month |
| **Server (Railway)** | $5-10 | Or use free tier |
| **ngrok Free** | $0 | For local testing only |
| **TOTAL** | **$0-10/month** | Free for light usage |

### When You'll Need to Upgrade Alchemy

- Tracking 50+ high-volume tokens
- Millions of transfers per month
- Sub-second latency requirements

Alchemy Growth plan: $49/month (1.5B compute units)

---

## 🔒 Security Best Practices

1. **Never commit API keys** to git
2. **Use signature verification** (already implemented)
3. **Whitelist IPs** in production (Alchemy dashboard → Settings)
4. **Use HTTPS** for webhooks (not HTTP)
5. **Rotate keys periodically** (every 90 days)

---

## 📚 Architecture Overview

```
┌─────────────────────────────────────────┐
│         Ethereum Blockchain             │
│  (LIT Token, Treasury, Deployer)        │
└─────────────────┬───────────────────────┘
                  │
                  │ Events
                  ↓
┌─────────────────────────────────────────┐
│         Alchemy Node Service            │
│  - Monitors blockchain in real-time     │
│  - Filters events for tracked addresses │
└─────────────────┬───────────────────────┘
                  │
                  │ HTTP POST (Webhook)
                  ↓
┌─────────────────────────────────────────┐
│   alchemy_webhook_server.py (Port 8080) │
│  - Receives webhook events              │
│  - Verifies signatures                  │
│  - Processes events                     │
└─────────────────┬───────────────────────┘
                  │
                  │ Database lookup
                  ↓
┌─────────────────────────────────────────┐
│      SQLite Database                    │
│  - evm_tracked_addresses table          │
│  - Maps addresses to users              │
└─────────────────┬───────────────────────┘
                  │
                  │ Get tracking users
                  ↓
┌─────────────────────────────────────────┐
│         Notifier (bot/notifier.py)      │
│  - Formats notifications                │
│  - Sends to Telegram                    │
└─────────────────┬───────────────────────┘
                  │
                  │ Telegram Bot API
                  ↓
┌─────────────────────────────────────────┐
│    Telegram Channel/Group               │
│    "CA Tracking" topic                  │
└─────────────────────────────────────────┘
```

---

## 🎓 Next Steps

1. ✅ Complete setup above
2. ✅ Run `/track_lit` to start tracking
3. ✅ Wait for first LIT treasury movement
4. Optional: Add more tokens with `/add_evm_address`
5. Optional: Deploy to production server (Railway, Render, etc.)

---

## 🆘 Support

If you encounter issues:

1. Check logs: `tail -f hypertracker.log`
2. Verify configuration: `.env` file
3. Test webhook: Alchemy dashboard → Test Webhook
4. Check database: `sqlite3 data/hypertracker.db`

Happy tracking! 🚀

# Quick Start: EVM Tracking for LIT Token

## TL;DR Setup (5 minutes)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Alchemy
1. Go to https://www.alchemy.com/ and create account
2. Create app: "HyperTracker EVM" on Ethereum Mainnet
3. Copy your API key

### 3. Set Up Webhook (Choose One)

**Option A: Local Testing with ngrok**
```bash
# Terminal 1
ngrok http 8080

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
```

**Option B: Production Server**
- Use your server's public URL

### 4. Create Alchemy Webhook
1. Go to Alchemy Dashboard → Notify tab
2. Click "Create Webhook" → "Address Activity"
3. Enter webhook URL: `https://your-url.com/alchemy-webhook`
4. Add addresses to monitor:
   ```
   0x232CE3bd40fCd6f80f3d55A522d03f25Df784Ee2  (LIT Token)
   0x077842A5670CB4C83dca62bDA4c36592a5B31891  (LIT Treasury)
   0x004Fe354757574E2DEB35fDb304383366f313099  (LIT Deployer)
   ```
5. Test webhook → should see 200 OK
6. Copy the Signing Key

### 5. Update .env
```bash
# Add to your .env file
ALCHEMY_API_KEY=your_api_key_here
ALCHEMY_SIGNING_KEY=your_signing_key_here
ALCHEMY_NETWORK=eth-mainnet

# Optional: Set CA tracking channel
CA_TRACKING_CHAT_ID=-1001234567890:12345
```

### 6. Run Both Services
```bash
# Terminal 1: Main bot
python run.py

# Terminal 2: Webhook server
python alchemy_webhook_server.py
```

### 7. Start Tracking
Send to your bot:
```
/track_lit
```

Done! You'll now get real-time alerts when LIT token moves.

---

## What You'll Get Notified About

✅ **Treasury movements** (🔐 → 🦄 DEX = liquidity addition!)
✅ **Large transfers** (>$10k movements)
✅ **CEX deposits** (potential dumps)
✅ **Deployer activity** (new contracts, transfers)
✅ **Token burns** (supply reduction)

---

## Testing

1. **Check webhook is working:**
   ```bash
   curl http://localhost:8080/health
   # Should return: {"status":"healthy"}
   ```

2. **Track LIT:**
   ```
   /track_lit
   # Should confirm: "✅ Now tracking LIT token activities!"
   ```

3. **List tracked:**
   ```
   /list_evm
   # Should show 3 addresses (Token, Treasury, Deployer)
   ```

---

## Production Deployment

Use PM2 to run both processes:

```bash
pm2 start run.py --name hypertracker-bot --interpreter python3
pm2 start alchemy_webhook_server.py --name alchemy-webhook --interpreter python3
pm2 save
pm2 startup  # Auto-start on server reboot
```

---

## Cost

**FREE for tracking LIT** (Alchemy free tier: 300M compute units/month)

Only need to pay if:
- Tracking 50+ tokens
- High-volume tokens (millions of transfers)

---

## Troubleshooting

**Webhook not receiving events?**
- Check webhook server: `curl http://localhost:8080/health`
- Check Alchemy dashboard → Notify → Recent Deliveries
- Verify signing key matches in `.env`

**Database errors?**
- Backup: `cp data/hypertracker.db data/hypertracker.db.backup`
- Restart: `python run.py` (auto-creates new tables)

**Need help?**
- See full guide: [EVM_TRACKING_SETUP.md](EVM_TRACKING_SETUP.md)
- Check logs: `tail -f hypertracker.log | grep -i alchemy`

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `/track_lit` | Track LIT token (adds all 3 addresses) |
| `/add_evm_address` | Track custom Ethereum address |
| `/list_evm` | Show all tracked addresses |
| `/stop_evm_tracking` | Stop tracking an address |
| `/evm_help` | Show EVM tracking help |

---

That's it! You're now tracking LIT token in real-time. 🚀

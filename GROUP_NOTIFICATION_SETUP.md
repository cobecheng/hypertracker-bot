# Group/Topic Notification Setup Guide

This guide explains how to configure HyperTracker Bot to send notifications to specific Telegram groups or topics.

## Overview

You can now configure the bot to send different types of notifications to different destinations:
- **Trade notifications** (fills, deposits, withdrawals) → One destination
- **Liquidation notifications** → Another destination

Each destination can be:
1. User's private chat (default)
2. A Telegram group
3. A specific topic within a Telegram group (supergroup with topics enabled)

## Quick Setup

### 1. Get Your Group/Topic IDs

#### Method 1: Using a Bot (Easiest)

1. Add [@userinfobot](https://t.me/userinfobot) to your group
2. Forward any message from the group to @userinfobot
3. It will show you the `Chat` ID (this is your group chat ID)
4. For topics: Send a message in the specific topic, forward it to @userinfobot
5. It will show both `Chat` and `TopicID` (thread ID)

#### Method 2: Using Web Telegram

1. Open [web.telegram.org](https://web.telegram.org)
2. Navigate to your group
3. Look at the URL: `https://web.telegram.org/a/#-1001234567890`
4. The number after `#` is your chat ID: `-1001234567890`
5. For topics: Click on a topic, the URL becomes: `https://web.telegram.org/a/#-1001234567890_12345`
6. The number after `_` is your topic/thread ID: `12345`

### 2. Add Bot to Your Group

1. Open your Telegram group
2. Click "Add Members" or group settings
3. Search for your bot (@your_bot_name)
4. Add the bot to the group
5. **Important**: Make sure the bot has permission to send messages in the group

### 3. Get Your Telegram User ID

To whitelist yourself, you need your Telegram user ID:

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID (a number like `123456789`)
3. Save this number - you'll need it for the `.env` file

### 4. Configure .env File

Edit your `.env` file and add the configuration:

```bash
# Your Telegram user ID (only your notifications go to the group)
WHITELISTED_USER_ID=123456789

# Group/topic destinations
TRADES_CHAT_ID=-1003041883586:3
LIQUIDATIONS_CHAT_ID=-1003041883586:34
```

**How it works:**
- **Your notifications** (user ID = `WHITELISTED_USER_ID`) → Go to group topics
- **Other users' notifications** → Go to their private chat with the bot

**Examples:**

```bash
# Example 1: Only you get group notifications, others get private chat
WHITELISTED_USER_ID=123456789
TRADES_CHAT_ID=-1001234567890:12345
LIQUIDATIONS_CHAT_ID=-1001234567890:67890

# Example 2: Everyone's notifications go to the group (not recommended)
WHITELISTED_USER_ID=
TRADES_CHAT_ID=-1001234567890
LIQUIDATIONS_CHAT_ID=-1001234567890

# Example 3: Everyone gets private chat (original behavior)
WHITELISTED_USER_ID=
TRADES_CHAT_ID=
LIQUIDATIONS_CHAT_ID=
```

### 5. Restart the Bot

```bash
# If running with docker-compose
docker-compose restart

# If running manually
# Stop the bot (Ctrl+C) and restart
python run.py
```

## Configuration Format

### For Regular Groups
```
TRADES_CHAT_ID=-1001234567890
```

### For Topics (Supergroups with Forum/Topics Enabled)
```
TRADES_CHAT_ID=-1001234567890:12345
```
- First number: Group chat ID
- Second number (after `:`): Topic/thread ID

### Leave Empty for Private Chat
```
TRADES_CHAT_ID=
```
If you leave it empty or don't set it, notifications will go to the user's private chat with the bot (default behavior).

## How It Works

1. **You manage the bot via private messages**: Add wallets, configure filters, etc.
2. **Whitelisting controls who gets group notifications**:
   - If `WHITELISTED_USER_ID` is set → Only that user's notifications go to the group
   - Other users' notifications → Always go to their private chat
   - If `WHITELISTED_USER_ID` is empty → All users' notifications go to the group (if configured)
3. **Notifications routing**:
   - **Whitelisted user**: Follows `TRADES_CHAT_ID` and `LIQUIDATIONS_CHAT_ID` settings
   - **Non-whitelisted users**: Always private chat, regardless of group settings
   - If chat IDs are empty → Falls back to private chat

## Example Use Cases

### Use Case 1: Report to Boss in Group Topics (Your Recommended Setup)
```bash
# Only your notifications go to the group
WHITELISTED_USER_ID=123456789

# Trades go to "Trading Alerts" topic
TRADES_CHAT_ID=-1001234567890:12345

# Liquidations go to "Market Events" topic
LIQUIDATIONS_CHAT_ID=-1001234567890:67890
```
**Result**: Your tracked wallets send notifications to the group topics. If someone else uses the bot, their notifications go to their private chat only.

### Use Case 2: Separate Groups for Different Notification Types
```bash
# Trades to one group
TRADES_CHAT_ID=-1001111111111

# Liquidations to another group
LIQUIDATIONS_CHAT_ID=-1002222222222
```

### Use Case 3: Only Override One Type
```bash
# Trades go to group
TRADES_CHAT_ID=-1001234567890

# Liquidations stay in private chat
LIQUIDATIONS_CHAT_ID=
```

## Troubleshooting

### Bot doesn't send messages to the group

1. **Check bot permissions**: Make sure the bot can send messages in the group
2. **Check chat ID format**:
   - Groups usually start with `-100`
   - Must be negative number
   - Format: `-1001234567890` or `-1001234567890:12345` for topics
3. **Check logs**: Look at `hypertracker.log` for errors
4. **Test with a simple message**: Temporarily add a test send in the code to verify the chat ID works

### Messages go to wrong topic

1. **Verify thread ID**: Make sure you copied the correct thread ID from the topic
2. **Topics must be enabled**: Only supergroups with "Topics" enabled support this
3. **Format must be exact**: `chat_id:thread_id` with colon separator

### Bot was removed from group

Check the logs - you'll see `TelegramForbiddenError`. Re-add the bot to the group.

## Notes

- **Privacy**: Only you (the bot owner) can interact with the bot via commands
- **Notifications**: Anyone in the group can see the notifications
- **Rate Limits**: Telegram has rate limits; the bot handles this automatically with delays
- **Topics**: Only work in supergroups with Topics/Forum mode enabled
- **Original behavior preserved**: If you don't set these env vars, everything works as before (private chat)

## Security Considerations

1. **Keep .env file secure**: Contains your bot token and group IDs
2. **Group admin rights**: Make sure only trusted admins can remove/modify bot permissions
3. **Topic permissions**: Configure topic permissions if you want to restrict who can see certain notifications
4. **Bot token**: Never share your `BOT_TOKEN` - anyone with it can control your bot

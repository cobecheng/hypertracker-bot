# Token Distribution Quickstart

This module adds a historical token-distribution workflow beside the existing HyperTracker bot.

## What it does

- Tracks ERC-20 `Transfer` logs in the first fixed window after launch
- Auto-discovers genesis roots from mint recipients if you do not provide treasury/root wallets
- Buckets end-of-window holders into:
  - Roots / treasury
  - DEX liquidity pools
  - Centralized exchange wallets
  - Unlabeled whales
  - Retail-like EOAs
  - Other contracts / unknowns
- Saves a JSON payload for a presentation dashboard

## First run

1. Configure an RPC source

```bash
export ETH_RPC_URL="<your_rpc_url>"
```

Or set:

```bash
export ALCHEMY_API_KEY="..."
```

2. Run the sample `$BASED` analysis

```bash
./.conda-py311/bin/python scripts/analyze_token_distribution.py --project based_eth
```

3. Start the dashboard server

```bash
./.conda-py311/bin/python dashboard_server.py
```

4. Open:

`http://127.0.0.1:8090/token-distribution?project=based_eth`

## Notes

- The current `$BASED` example is Ethereum-first.
- The project’s official material describes a global fixed supply of `1,000,000,000 BASED`, while the Ethereum contract is an omnichain token representation. Treat chain-local supply and global disclosed supply separately.
- Exchange and market-maker detection improves as you extend `token_distribution/labels.py`.

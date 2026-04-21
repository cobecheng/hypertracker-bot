import { asNumber, buildErrorResponse, loadJson, query, sendJson } from "../_lib/db.js";

export default async function handler(req, res) {
  try {
    const limit = Math.min(Math.max(Number(req.query.limit || 25), 1), 100);
    const result = await query("select wallet_address, positions_json from public.wallet_live_snapshots");
    const exposures = new Map();

    for (const row of result.rows) {
      const positions = loadJson(row.positions_json);
      const seenAssets = new Set();
      for (const position of positions) {
        const coin = position.coin;
        if (!coin) continue;
        if (!exposures.has(coin)) {
          exposures.set(coin, {
            coin,
            wallets_count: 0,
            long_usd: 0,
            short_usd: 0,
            net_usd: 0,
          });
        }
        const data = exposures.get(coin);
        if (!seenAssets.has(coin)) {
          data.wallets_count += 1;
          seenAssets.add(coin);
        }
        const notional = asNumber(position.position_notional_usd);
        if (position.direction === "long") {
          data.long_usd += notional;
          data.net_usd += notional;
        } else if (position.direction === "short") {
          data.short_usd += notional;
          data.net_usd -= notional;
        }
      }
    }

    const items = [...exposures.values()]
      .sort((a, b) => Math.abs(b.net_usd) - Math.abs(a.net_usd))
      .slice(0, limit);

    return sendJson(res, { items });
  } catch (error) {
    const failure = buildErrorResponse(error);
    return sendJson(res, failure.body, failure.statusCode);
  }
}

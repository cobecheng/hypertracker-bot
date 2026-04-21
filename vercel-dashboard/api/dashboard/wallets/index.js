import { asNumber, buildErrorResponse, loadJson, parseWindowStart, query, sendJson } from "../../_lib/db.js";

async function getWalletLiveSnapshot(walletId) {
  const result = await query("select * from public.wallet_live_snapshots where wallet_id = $1", [walletId]);
  const row = result.rows[0];
  if (!row) return null;
  return {
    wallet_id: asNumber(row.wallet_id),
    user_id: asNumber(row.user_id),
    wallet_address: row.wallet_address,
    account_value: asNumber(row.account_value),
    total_notional_usd: asNumber(row.total_notional_usd),
    total_margin_used: asNumber(row.total_margin_used),
    withdrawable: asNumber(row.withdrawable),
    positions_count: asNumber(row.positions_count),
    long_positions_count: asNumber(row.long_positions_count),
    short_positions_count: asNumber(row.short_positions_count),
    net_exposure_bias: row.net_exposure_bias,
    positions: loadJson(row.positions_json),
    snapshot_time_ms: row.snapshot_time_ms ? Number(row.snapshot_time_ms) : null,
  };
}

export default async function handler(req, res) {
  try {
    const window = req.query.window || "1h";
    const limit = Math.min(Math.max(Number(req.query.limit || 100), 1), 300);
    const startTimeMs = parseWindowStart(window);
    const result = await query(
      `
      select
        w.id, w.user_id, w.address, w.alias,
        count(e.id) as fills_count,
        count(distinct e.coin) as assets_count,
        max(e.event_time_ms) as last_event_time_ms,
        coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) as buy_usd,
        coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0) as sell_usd
      from public.wallets w
      left join public.wallet_fill_events e on e.wallet_id = w.id and e.event_time_ms >= $1
      where w.active = true
      group by w.id, w.user_id, w.address, w.alias, w.created_at
      order by abs(
        coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) -
        coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0)
      ) desc, fills_count desc, w.created_at desc
      limit $2
      `,
      [startTimeMs, limit],
    );

    const items = [];
    for (const row of result.rows) {
      const buy = asNumber(row.buy_usd);
      const sell = asNumber(row.sell_usd);
      items.push({
        id: asNumber(row.id),
        user_id: asNumber(row.user_id),
        address: row.address,
        alias: row.alias,
        fills_count: asNumber(row.fills_count),
        assets_count: asNumber(row.assets_count),
        last_event_time_ms: row.last_event_time_ms ? Number(row.last_event_time_ms) : null,
        buy_usd: buy,
        sell_usd: sell,
        net_flow_usd: buy - sell,
        live: await getWalletLiveSnapshot(asNumber(row.id)),
      });
    }

    return sendJson(res, { items });
  } catch (error) {
    const failure = buildErrorResponse(error);
    return sendJson(res, failure.body, failure.statusCode);
  }
}

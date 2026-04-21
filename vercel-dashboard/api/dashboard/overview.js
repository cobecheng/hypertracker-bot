import { asNumber, buildErrorResponse, parseWindowStart, query, sendJson } from "../_lib/db.js";

export default async function handler(req, res) {
  try {
    const window = req.query.window || "1h";
    const startTimeMs = parseWindowStart(window);
    const result = await query(
      `
      select
        count(distinct w.id) as tracked_wallets,
        count(distinct case when e.id is not null then w.id end) as active_wallets,
        count(distinct e.coin) as active_assets,
        count(e.id) as total_fills,
        coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) as total_buy_usd,
        coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0) as total_sell_usd
      from public.wallets w
      left join public.wallet_fill_events e
        on e.wallet_id = w.id and e.event_time_ms >= $1
      where w.active = true
      `,
      [startTimeMs],
    );
    const row = result.rows[0] || {};
    const buy = asNumber(row.total_buy_usd);
    const sell = asNumber(row.total_sell_usd);
    return sendJson(res, {
      tracked_wallets: asNumber(row.tracked_wallets),
      active_wallets: asNumber(row.active_wallets),
      active_assets: asNumber(row.active_assets),
      total_fills: asNumber(row.total_fills),
      total_buy_usd: buy,
      total_sell_usd: sell,
      net_flow_usd: buy - sell,
    });
  } catch (error) {
    const failure = buildErrorResponse(error);
    return sendJson(res, failure.body, failure.statusCode);
  }
}

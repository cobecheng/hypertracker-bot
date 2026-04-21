import { asNumber, buildErrorResponse, parseWindowStart, query, sendJson } from "../_lib/db.js";

export default async function handler(req, res) {
  try {
    const window = req.query.window || "1h";
    const limit = Math.min(Math.max(Number(req.query.limit || 25), 1), 100);
    const startTimeMs = parseWindowStart(window);
    const result = await query(
      `
      select
        e.coin,
        count(*) as fills_count,
        count(distinct e.wallet_id) as wallets_count,
        coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) as buy_usd,
        coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0) as sell_usd
      from public.wallet_fill_events e
      inner join public.wallets w on w.id = e.wallet_id
      where w.active = true and e.event_time_ms >= $1
      group by e.coin
      order by abs(
        coalesce(sum(case when e.side = 'B' then e.notional_usd else 0 end), 0) -
        coalesce(sum(case when e.side = 'A' then e.notional_usd else 0 end), 0)
      ) desc, fills_count desc
      limit $2
      `,
      [startTimeMs, limit],
    );
    return sendJson(res, {
      items: result.rows.map((row) => {
        const buy = asNumber(row.buy_usd);
        const sell = asNumber(row.sell_usd);
        return {
          coin: row.coin,
          fills_count: asNumber(row.fills_count),
          wallets_count: asNumber(row.wallets_count),
          buy_usd: buy,
          sell_usd: sell,
          net_flow_usd: buy - sell,
        };
      }),
    });
  } catch (error) {
    const failure = buildErrorResponse(error);
    return sendJson(res, failure.body, failure.statusCode);
  }
}

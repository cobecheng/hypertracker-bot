import { asNumber, buildErrorResponse, parseWindowStart, query, sendJson } from "../_lib/db.js";

export default async function handler(req, res) {
  try {
    const window = req.query.window || "1h";
    const limit = Math.min(Math.max(Number(req.query.limit || 50), 1), 200);
    const startTimeMs = parseWindowStart(window);
    const result = await query(
      `
      select e.wallet_id, w.alias, w.address, e.coin, e.side, e.price, e.size, e.notional_usd, e.event_time_ms, e.dir
      from public.wallet_fill_events e
      inner join public.wallets w on w.id = e.wallet_id
      where w.active = true and e.event_time_ms >= $1
      order by e.event_time_ms desc, e.id desc
      limit $2
      `,
      [startTimeMs, limit],
    );

    return sendJson(res, {
      items: result.rows.map((row) => ({
        wallet_id: asNumber(row.wallet_id),
        alias: row.alias,
        address: row.address,
        coin: row.coin,
        side: row.side,
        price: asNumber(row.price),
        size: asNumber(row.size),
        notional_usd: asNumber(row.notional_usd),
        event_time_ms: row.event_time_ms ? Number(row.event_time_ms) : null,
        dir: row.dir,
      })),
    });
  } catch (error) {
    const failure = buildErrorResponse(error);
    return sendJson(res, failure.body, failure.statusCode);
  }
}

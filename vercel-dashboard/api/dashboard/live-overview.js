import { asNumber, buildErrorResponse, query, sendJson } from "../_lib/db.js";

export default async function handler(_req, res) {
  try {
    const result = await query(
      `
      select
        count(*) as wallets_with_snapshot,
        coalesce(sum(account_value), 0) as total_account_value,
        coalesce(sum(total_notional_usd), 0) as total_notional_usd,
        coalesce(sum(case when net_exposure_bias = 'long' then 1 else 0 end), 0) as net_long_wallets,
        coalesce(sum(case when net_exposure_bias = 'short' then 1 else 0 end), 0) as net_short_wallets,
        coalesce(sum(positions_count), 0) as total_open_positions,
        max(snapshot_time_ms) as latest_snapshot_time_ms
      from public.wallet_live_snapshots
      `,
    );
    const row = result.rows[0] || {};
    return sendJson(res, {
      wallets_with_snapshot: asNumber(row.wallets_with_snapshot),
      total_account_value: asNumber(row.total_account_value),
      total_notional_usd: asNumber(row.total_notional_usd),
      net_long_wallets: asNumber(row.net_long_wallets),
      net_short_wallets: asNumber(row.net_short_wallets),
      total_open_positions: asNumber(row.total_open_positions),
      latest_snapshot_time_ms: row.latest_snapshot_time_ms ? Number(row.latest_snapshot_time_ms) : null,
    });
  } catch (error) {
    const failure = buildErrorResponse(error);
    return sendJson(res, failure.body, failure.statusCode);
  }
}

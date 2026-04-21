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
    const walletId = Number(req.query.walletId);
    if (!walletId) {
      return sendJson(res, { error: "Wallet not found" }, 404);
    }
    const window = req.query.window || "1h";
    const startTimeMs = parseWindowStart(window);

    const walletResult = await query(
      "select id, user_id, address, alias, active from public.wallets where id = $1",
      [walletId],
    );
    const walletRow = walletResult.rows[0];
    if (!walletRow) {
      return sendJson(res, { error: "Wallet not found" }, 404);
    }

    const summaryResult = await query(
      `
      select count(*) as fills_count, count(distinct coin) as assets_count, max(event_time_ms) as last_event_time_ms,
             coalesce(sum(case when side='B' then notional_usd else 0 end),0) as buy_usd,
             coalesce(sum(case when side='A' then notional_usd else 0 end),0) as sell_usd
      from public.wallet_fill_events where wallet_id = $1 and event_time_ms >= $2
      `,
      [walletId, startTimeMs],
    );
    const assetResult = await query(
      `
      select coin, count(*) as fills_count,
             coalesce(sum(case when side='B' then notional_usd else 0 end),0) as buy_usd,
             coalesce(sum(case when side='A' then notional_usd else 0 end),0) as sell_usd
      from public.wallet_fill_events
      where wallet_id = $1 and event_time_ms >= $2
      group by coin
      order by abs(
        coalesce(sum(case when side='B' then notional_usd else 0 end),0) -
        coalesce(sum(case when side='A' then notional_usd else 0 end),0)
      ) desc, fills_count desc
      `,
      [walletId, startTimeMs],
    );
    const recentResult = await query(
      `
      select coin, side, price, size, notional_usd, event_time_ms, dir
      from public.wallet_fill_events
      where wallet_id = $1 and event_time_ms >= $2
      order by event_time_ms desc, id desc
      limit 20
      `,
      [walletId, startTimeMs],
    );
    const summaryRow = summaryResult.rows[0] || {};
    const buy = asNumber(summaryRow.buy_usd);
    const sell = asNumber(summaryRow.sell_usd);

    return sendJson(res, {
      wallet: {
        id: asNumber(walletRow.id),
        user_id: asNumber(walletRow.user_id),
        address: walletRow.address,
        alias: walletRow.alias,
        active: Boolean(walletRow.active),
      },
      summary: {
        fills_count: asNumber(summaryRow.fills_count),
        assets_count: asNumber(summaryRow.assets_count),
        last_event_time_ms: summaryRow.last_event_time_ms ? Number(summaryRow.last_event_time_ms) : null,
        buy_usd: buy,
        sell_usd: sell,
        net_flow_usd: buy - sell,
      },
      live: await getWalletLiveSnapshot(walletId),
      assets: assetResult.rows.map((row) => {
        const assetBuy = asNumber(row.buy_usd);
        const assetSell = asNumber(row.sell_usd);
        return {
          coin: row.coin,
          fills_count: asNumber(row.fills_count),
          buy_usd: assetBuy,
          sell_usd: assetSell,
          net_flow_usd: assetBuy - assetSell,
        };
      }),
      recent_fills: recentResult.rows.map((row) => ({
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

const state = {
  window: "1h",
  walletLimit: 100,
  selectedWalletId: null,
};

const overviewGrid = document.getElementById("overview-grid");
const liveOverviewGrid = document.getElementById("live-overview-grid");
const assetList = document.getElementById("asset-list");
const liveAssetList = document.getElementById("live-asset-list");
const walletTableBody = document.getElementById("wallet-table-body");
const activityFeed = document.getElementById("activity-feed");
const updatedAt = document.getElementById("updated-at");
const refreshButton = document.getElementById("refresh-button");
const drawer = document.getElementById("wallet-drawer");
const drawerClose = document.getElementById("drawer-close");
const drawerBackdrop = document.getElementById("drawer-backdrop");

function money(value) {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}

function shortAddress(address) {
  return `${address.slice(0, 8)}...${address.slice(-6)}`;
}

function canonicalCoin(coin) {
  if (!coin) return "UNKNOWN";
  return String(coin).split(":").pop();
}

function renderCoinLabel(coin) {
  const canonical = canonicalCoin(coin);
  if (canonical === coin) {
    return canonical;
  }
  return `${canonical} <span class="coin-alias">${coin}</span>`;
}

function relativeTime(timestampMs) {
  if (!timestampMs) return "No recent fills";
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - timestampMs) / 1000));
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  if (deltaSeconds < 3600) return `${Math.floor(deltaSeconds / 60)}m ago`;
  if (deltaSeconds < 86400) return `${Math.floor(deltaSeconds / 3600)}h ago`;
  return `${Math.floor(deltaSeconds / 86400)}d ago`;
}

function flowClass(value) {
  if (value > 0) return "buy";
  if (value < 0) return "sell";
  return "flat";
}

function flowLabel(value) {
  if (value > 0) return "Net Buy";
  if (value < 0) return "Net Sell";
  return "Flat";
}

function setUpdatedAt() {
  updatedAt.textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function renderOverview(data) {
  const items = [
    ["Tracked Wallets", data.tracked_wallets, ""],
    ["Active Wallets", data.active_wallets, ""],
    ["Active Assets", data.active_assets, ""],
    ["Total Fills", data.total_fills, ""],
    ["Total Buy", money(data.total_buy_usd), "buy"],
    ["Total Sell", money(data.total_sell_usd), "sell"],
    ["Net Flow", money(data.net_flow_usd), flowClass(data.net_flow_usd)],
  ];

  overviewGrid.innerHTML = items.map(([label, value, klass]) => `
    <div class="metric-card">
      <div class="metric-label">${label}</div>
      <div class="metric-value ${klass}">${value}</div>
    </div>
  `).join("");
}

function renderAssets(items) {
  if (!items.length) {
    assetList.innerHTML = `<div class="empty-state">No asset activity in this window yet.</div>`;
    return;
  }

  assetList.innerHTML = items.map((asset) => `
    <div class="asset-row">
      <div>
        <div class="asset-name">${renderCoinLabel(asset.coin)}</div>
        <div class="asset-meta">${asset.wallets_count} wallet(s) • ${asset.fills_count} fills</div>
      </div>
      <div class="asset-meta">Buy ${money(asset.buy_usd)}<br />Sell ${money(asset.sell_usd)}</div>
      <div class="flow-pill ${flowClass(asset.net_flow_usd)}">${flowLabel(asset.net_flow_usd)} ${money(asset.net_flow_usd)}</div>
    </div>
  `).join("");
}

function renderLiveOverview(data) {
  const items = [
    ["Snapshots", data.wallets_with_snapshot, ""],
    ["Open Positions", data.total_open_positions, ""],
    ["Net Long Wallets", data.net_long_wallets, "buy"],
    ["Net Short Wallets", data.net_short_wallets, "sell"],
    ["Account Value", money(data.total_account_value), ""],
    ["Open Notional", money(data.total_notional_usd), ""],
    ["Last Snapshot", data.latest_snapshot_time_ms ? relativeTime(data.latest_snapshot_time_ms) : "Waiting...", ""],
  ];

  liveOverviewGrid.innerHTML = items.map(([label, value, klass]) => `
    <div class="metric-card">
      <div class="metric-label">${label}</div>
      <div class="metric-value ${klass}">${value}</div>
    </div>
  `).join("");
}

function renderLiveAssets(items) {
  if (!items.length) {
    liveAssetList.innerHTML = `<div class="empty-state">Waiting for live snapshots to populate.</div>`;
    return;
  }

  liveAssetList.innerHTML = items.map((asset) => `
    <div class="asset-row">
      <div>
        <div class="asset-name">${renderCoinLabel(asset.coin)}</div>
        <div class="asset-meta">${asset.wallets_count} wallet(s) live</div>
      </div>
      <div class="asset-meta">Long ${money(asset.long_usd)}<br />Short ${money(asset.short_usd)}</div>
      <div class="flow-pill ${flowClass(asset.net_usd)}">${flowLabel(asset.net_usd)} ${money(asset.net_usd)}</div>
    </div>
  `).join("");
}

function renderWallets(items) {
  if (!items.length) {
    walletTableBody.innerHTML = `<tr><td colspan="7"><div class="empty-state">No wallet activity in this window yet.</div></td></tr>`;
    return;
  }

  walletTableBody.innerHTML = items.map((wallet) => `
    <tr class="wallet-row" data-wallet-id="${wallet.id}">
      <td>
        <div class="wallet-name">${wallet.alias || shortAddress(wallet.address)}</div>
        <div class="wallet-subline mono">${shortAddress(wallet.address)}</div>
      </td>
      <td><span class="flow-pill ${flowClass(wallet.net_flow_usd)}">${money(wallet.net_flow_usd)}</span></td>
      <td>${money(wallet.buy_usd)}</td>
      <td>${money(wallet.sell_usd)}</td>
      <td>${wallet.live ? `<span class="flow-pill ${flowClass(wallet.live.net_exposure_bias === "long" ? 1 : wallet.live.net_exposure_bias === "short" ? -1 : 0)}">${wallet.live.net_exposure_bias}</span>` : '<span class="wallet-subline">Waiting...</span>'}</td>
      <td>${wallet.live ? wallet.live.positions_count : "-"}</td>
      <td>${wallet.live ? money(wallet.live.account_value) : "-"}</td>
      <td>${wallet.assets_count}</td>
      <td>${wallet.fills_count}</td>
      <td>${relativeTime(wallet.last_event_time_ms)}</td>
    </tr>
  `).join("");

  for (const row of document.querySelectorAll(".wallet-row")) {
    row.addEventListener("click", () => openWalletDetail(row.dataset.walletId));
  }
}

function renderRecentFills(items) {
  if (!items.length) {
    activityFeed.innerHTML = `<div class="empty-state">No recent fills in this window.</div>`;
    return;
  }

  activityFeed.innerHTML = items.map((fill) => {
    const netClass = fill.side === "B" ? "buy" : "sell";
    const label = fill.side === "B" ? "Buy" : "Sell";
    return `
      <div class="activity-row">
        <div>
          <div class="wallet-name">${fill.alias || shortAddress(fill.address)} • ${canonicalCoin(fill.coin)}</div>
          <div class="activity-meta">${fill.dir || label} • ${shortAddress(fill.address)}</div>
        </div>
        <div class="flow-pill ${netClass}">${label} ${money(fill.notional_usd)}</div>
        <div class="activity-meta">${relativeTime(fill.event_time_ms)}</div>
      </div>
    `;
  }).join("");
}

function renderDrawer(detail) {
  document.getElementById("drawer-title").textContent = detail.wallet.alias || shortAddress(detail.wallet.address);
  document.getElementById("drawer-subtitle").textContent = detail.wallet.address;

  const summary = detail.summary;
  document.getElementById("drawer-summary").innerHTML = [
    ["Net Flow", money(summary.net_flow_usd), flowClass(summary.net_flow_usd)],
    ["Total Buy", money(summary.buy_usd), "buy"],
    ["Total Sell", money(summary.sell_usd), "sell"],
    ["Fills", summary.fills_count, ""],
  ].map(([label, value, klass]) => `
    <div class="metric-card">
      <div class="metric-label">${label}</div>
      <div class="metric-value ${klass}">${value}</div>
    </div>
  `).join("");

  const live = detail.live;
  const liveCoinSet = new Set((live?.positions || []).map((position) => canonicalCoin(position.coin)));
  document.getElementById("drawer-live").innerHTML = live && live.positions && live.positions.length
    ? live.positions.map((position) => `
        <div class="drawer-row live-position">
          <div>
            <div class="drawer-asset-name">${renderCoinLabel(position.coin)} • <span class="position-side ${position.direction === "long" ? "long" : "short"}">${position.direction}</span></div>
            <div class="drawer-muted">Size ${position.size.toLocaleString()} @ $${position.entry_px.toLocaleString()}</div>
            <div class="drawer-muted">Unrealized PnL <span class="position-pnl ${flowClass(position.unrealized_pnl_usd)}">${money(position.unrealized_pnl_usd)}</span></div>
          </div>
          <div class="flow-pill ${flowClass(position.direction === "long" ? 1 : -1)}">${money(position.position_notional_usd)}</div>
        </div>
      `).join("")
    : `<div class="empty-state">No open positions in the latest live snapshot yet.</div>`;

  const assets = detail.assets || [];
  document.getElementById("drawer-assets").innerHTML = assets.length
    ? assets.map((asset) => {
        const isLive = liveCoinSet.has(canonicalCoin(asset.coin));
        return `
        <div class="drawer-row">
          <div>
            <div class="drawer-asset-name">${renderCoinLabel(asset.coin)}</div>
            <div class="drawer-muted">${asset.fills_count} fills • <span class="asset-status ${isLive ? "is-live" : "not-live"}">${isLive ? "Still open live" : "No live position in latest snapshot"}</span></div>
          </div>
          <div class="flow-pill ${flowClass(asset.net_flow_usd)}">${money(asset.net_flow_usd)}</div>
        </div>
      `;
      }).join("")
    : `<div class="empty-state">No fills for this wallet in the selected window.</div>`;

  const fills = detail.recent_fills || [];
  document.getElementById("drawer-fills").innerHTML = fills.length
    ? fills.map((fill) => `
        <div class="drawer-row">
          <div>
            <div class="drawer-asset-name">${renderCoinLabel(fill.coin)} • ${fill.dir || (fill.side === "B" ? "Buy" : "Sell")}</div>
            <div class="drawer-muted">${relativeTime(fill.event_time_ms)}</div>
          </div>
          <div class="flow-pill ${fill.side === "B" ? "buy" : "sell"}">${money(fill.notional_usd)}</div>
        </div>
      `).join("")
    : `<div class="empty-state">No recent fills available.</div>`;
}

async function openWalletDetail(walletId) {
  state.selectedWalletId = walletId;
  const detail = await fetchJson(`/api/dashboard/wallets/${walletId}?window=${state.window}`);
  renderDrawer(detail);
  drawer.classList.remove("hidden");
}

function closeDrawer() {
  drawer.classList.add("hidden");
}

async function loadDashboard() {
  refreshButton.disabled = true;
  refreshButton.textContent = "Refreshing...";

  try {
    const [overview, liveOverview, assets, liveAssets, wallets, recentFills] = await Promise.all([
      fetchJson(`/api/dashboard/overview?window=${state.window}`),
      fetchJson(`/api/dashboard/live-overview`),
      fetchJson(`/api/dashboard/assets?window=${state.window}`),
      fetchJson(`/api/dashboard/live-assets`),
      fetchJson(`/api/dashboard/wallets?window=${state.window}&limit=${state.walletLimit}`),
      fetchJson(`/api/dashboard/recent-fills?window=${state.window}`),
    ]);

    renderOverview(overview);
    renderLiveOverview(liveOverview);
    renderAssets(assets.items);
    renderLiveAssets(liveAssets.items);
    renderWallets(wallets.items);
    renderRecentFills(recentFills.items);
    setUpdatedAt();

    if (state.selectedWalletId) {
      const detail = await fetchJson(`/api/dashboard/wallets/${state.selectedWalletId}?window=${state.window}`);
      renderDrawer(detail);
    }
  } catch (error) {
    console.error(error);
    overviewGrid.innerHTML = `<div class="empty-state">Dashboard load failed. Check the server logs and try refresh.</div>`;
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "Refresh";
  }
}

document.getElementById("window-picker").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-window]");
  if (!button) return;

  state.window = button.dataset.window;
  for (const item of document.querySelectorAll("#window-picker button")) {
    item.classList.toggle("active", item === button);
  }
  loadDashboard();
});

refreshButton.addEventListener("click", loadDashboard);
drawerClose.addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", closeDrawer);

loadDashboard();
setInterval(loadDashboard, 30000);

const state = {
  projectSlug: new URLSearchParams(window.location.search).get("project") || "based_eth",
  projects: [],
};

const projectSelect = document.getElementById("project-select");
const refreshButton = document.getElementById("refresh-button");
const setupPanel = document.getElementById("setup-panel");

function moneyish(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function pct(value) {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(2)}%`;
}

function shortAddress(address) {
  if (!address) return "—";
  return `${address.slice(0, 8)}...${address.slice(-6)}`;
}

function categoryLabel(category) {
  return String(category || "unknown").replaceAll("_", " ");
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function setStatus(status, copy) {
  const pill = document.getElementById("status-pill");
  pill.textContent = status;
  pill.dataset.status = status;
  document.getElementById("status-copy").textContent = copy;
}

function renderProjectHeader(payload) {
  const project = payload.project || {};
  document.getElementById("project-title").textContent = `${project.display_name || "Token"} (${project.symbol || "TOKEN"})`;
  document.getElementById("project-meta").textContent = `${project.chain_name || project.chain_slug || "Chain"} • ${project.slug || ""}`;
  document.getElementById("token-address").textContent = project.token_address || "—";
  document.getElementById("window-copy").textContent = project.window_days ? `${project.window_days} days from launch anchor` : "—";
  document.getElementById("root-count").textContent = Array.isArray(project.root_addresses) ? `${project.root_addresses.length} roots` : "—";

  const supply = payload.supply || {};
  document.getElementById("supply-basis").textContent = supply.supply_basis ? `${moneyish(supply.supply_basis, 2)} ${project.symbol || ""}` : "Awaiting analysis";

  const noteParts = [];
  if (project.notes) noteParts.push(project.notes);
  if (project.references?.length) {
    const refs = project.references
      .map((ref) => `<a href="${ref.url}" target="_blank" rel="noreferrer">${ref.title}</a>`)
      .join(" · ");
    noteParts.push(refs);
  }
  document.getElementById("notes-card").innerHTML = noteParts.length ? noteParts.join("<br />") : "No project notes yet.";
}

function renderMetrics(payload) {
  const summary = payload.summary || {};
  const project = payload.project || {};
  const metrics = [
    ["Roots / Treasury", `${moneyish(summary.roots_balance)} ${project.symbol || ""}`, pct(summary.roots_balance_pct)],
    ["Non-root Holders", `${moneyish(summary.non_root_balance)} ${project.symbol || ""}`, pct(summary.non_root_balance_pct)],
    ["Retail-like", `${moneyish(summary.retail_like_balance)} ${project.symbol || ""}`, pct(summary.retail_like_balance_pct)],
    ["Whales", `${moneyish(summary.whale_balance)} ${project.symbol || ""}`, pct(summary.whale_balance_pct)],
    ["CEX Wallets", `${moneyish(summary.cex_balance)} ${project.symbol || ""}`, pct(summary.cex_balance_pct)],
    ["DEX Liquidity", `${moneyish(summary.dex_liquidity_balance)} ${project.symbol || ""}`, pct(summary.dex_liquidity_balance_pct)],
  ];

  document.getElementById("metric-grid").innerHTML = metrics.map(([label, value, extra]) => `
    <div class="metric-card">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-meta">${extra}</div>
    </div>
  `).join("");
}

function renderBuckets(payload) {
  const project = payload.project || {};
  const items = payload.allocation_buckets || [];
  const container = document.getElementById("bucket-list");
  if (!items.length) {
    container.innerHTML = `<div class="empty-state">No bucket data yet.</div>`;
    return;
  }

  container.innerHTML = items.map((bucket) => `
    <div class="bucket-row">
      <div>
        <div class="bucket-title">${bucket.label}</div>
        <div class="bucket-meta">${bucket.holders} holders</div>
      </div>
      <div class="bucket-bar">
        <span style="width:${Math.max(3, Math.min(100, Number(bucket.balance_pct || 0)))}%"></span>
      </div>
      <div class="bucket-stat">${moneyish(bucket.balance)} ${project.symbol || ""}</div>
      <div class="bucket-stat">${pct(bucket.balance_pct)}</div>
    </div>
  `).join("");
}

function renderHolders(payload) {
  const project = payload.project || {};
  const items = payload.top_holders || [];
  const body = document.getElementById("holder-table-body");
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="5"><div class="empty-state">Top holder table will appear after a saved run.</div></td></tr>`;
    return;
  }

  body.innerHTML = items.map((holder) => `
    <tr>
      <td>
        <a href="${holder.explorer_url}" target="_blank" rel="noreferrer">${holder.label || shortAddress(holder.address)}</a>
        <div class="subtext mono">${shortAddress(holder.address)}</div>
      </td>
      <td><span class="pill">${categoryLabel(holder.category)}</span></td>
      <td>${moneyish(holder.balance)} ${project.symbol || ""}</td>
      <td>${pct(holder.balance_pct)}</td>
      <td>${holder.hop ?? "—"}</td>
    </tr>
  `).join("");
}

function renderRoutes(payload) {
  const project = payload.project || {};
  const items = payload.notable_routes || [];
  const container = document.getElementById("route-list");
  if (!items.length) {
    container.innerHTML = `<div class="empty-state">Notable routes appear once the analyzer has traced reachable wallets.</div>`;
    return;
  }

  container.innerHTML = items.map((route) => `
    <div class="route-card">
      <div>
        <div class="route-title"><a href="${route.explorer_url}" target="_blank" rel="noreferrer">${route.label || shortAddress(route.address)}</a></div>
        <div class="subtext">${categoryLabel(route.category)} • hop ${route.hop ?? "—"}${route.discovered_from_short ? ` • from ${route.discovered_from_short}` : ""}</div>
      </div>
      <div class="route-side">
        <div>${moneyish(route.received_from_roots)} ${project.symbol || ""} from roots</div>
        <div class="subtext">${moneyish(route.end_balance)} ${project.symbol || ""} end balance</div>
      </div>
    </div>
  `).join("");
}

function renderEdges(payload) {
  const project = payload.project || {};
  const items = payload.edges || [];
  const container = document.getElementById("edge-list");
  if (!items.length) {
    container.innerHTML = `<div class="empty-state">Edge summary will appear after a saved run.</div>`;
    return;
  }

  container.innerHTML = items.map((edge) => `
    <div class="route-card">
      <div>
        <div class="route-title">${edge.from_label || shortAddress(edge.from_address)} → ${edge.to_label || shortAddress(edge.to_address)}</div>
        <div class="subtext">${categoryLabel(edge.from_category)} → ${categoryLabel(edge.to_category)} • ${edge.transfer_count} transfers</div>
      </div>
      <div class="route-side">
        <div>${moneyish(edge.amount)} ${project.symbol || ""}</div>
        <div class="subtext"><a href="${edge.last_tx_url}" target="_blank" rel="noreferrer">latest tx</a></div>
      </div>
    </div>
  `).join("");
}

function renderTransfers(payload) {
  const project = payload.project || {};
  const items = payload.largest_transfers || [];
  const container = document.getElementById("transfer-list");
  if (!items.length) {
    container.innerHTML = `<div class="empty-state">Largest single transfers will appear after a saved run.</div>`;
    return;
  }

  container.innerHTML = items.map((transfer) => `
    <div class="route-card">
      <div>
        <div class="route-title"><a href="${transfer.explorer_url}" target="_blank" rel="noreferrer">${moneyish(transfer.amount)} ${project.symbol || ""}</a></div>
        <div class="subtext">${transfer.from_short} → ${transfer.to_short} • block ${transfer.block_number}</div>
      </div>
      <div class="route-side">
        <div>${new Date(transfer.timestamp_iso).toLocaleString()}</div>
      </div>
    </div>
  `).join("");
}

function renderDiagnostics(payload) {
  const diagnostics = payload.diagnostics || {};
  const setup = payload.setup || {};
  const items = [];
  if (diagnostics.rpc_source) items.push(`RPC source: ${diagnostics.rpc_source}`);
  if (diagnostics.label_note) items.push(diagnostics.label_note);
  if (diagnostics.roots_discovered?.length) items.push(`Auto-discovered roots: ${diagnostics.roots_discovered.length}`);
  if (diagnostics.warnings?.length) items.push(...diagnostics.warnings);
  if (setup.required_env?.length) items.push(`Required env: ${setup.required_env.join(", ")}`);

  document.getElementById("diagnostics-list").innerHTML = items.length
    ? items.map((item) => `<div class="diagnostic-row">${item}</div>`).join("")
    : `<div class="empty-state">No diagnostics for this payload.</div>`;
}

function renderSetup(payload) {
  const setup = payload.setup || {};
  const lines = [];
  if (setup.why_empty) lines.push(`<p>${setup.why_empty}</p>`);
  if (setup.required_env?.length) lines.push(`<p><strong>Required env:</strong> ${setup.required_env.join(", ")}</p>`);
  if (setup.recommended_command) lines.push(`<p><strong>Run:</strong> <code>${setup.recommended_command}</code></p>`);
  document.getElementById("setup-copy").innerHTML = lines.join("");
}

async function loadProjects() {
  const data = await fetchJson("/api/token-distribution/projects");
  state.projects = data.items || [];
  projectSelect.innerHTML = state.projects.map((project) => `
    <option value="${project.slug}" ${project.slug === state.projectSlug ? "selected" : ""}>${project.display_name} (${project.symbol})</option>
  `).join("");
}

async function loadCurrentProject() {
  const payload = await fetchJson(`/api/token-distribution/current?project_slug=${encodeURIComponent(state.projectSlug)}`);
  renderProjectHeader(payload);
  renderMetrics(payload);
  renderBuckets(payload);
  renderHolders(payload);
  renderRoutes(payload);
  renderEdges(payload);
  renderTransfers(payload);
  renderDiagnostics(payload);
  renderSetup(payload);

  const isReady = payload.status === "complete";
  setupPanel.classList.toggle("hidden", isReady);
  setStatus(
    payload.status || "unknown",
    isReady
      ? "Saved analysis loaded from the local token distribution output directory."
      : "This page is ready, but the underlying JSON result still needs to be generated.",
  );
}

async function boot() {
  await loadProjects();
  await loadCurrentProject();
}

projectSelect.addEventListener("change", async () => {
  state.projectSlug = projectSelect.value;
  const url = new URL(window.location.href);
  url.searchParams.set("project", state.projectSlug);
  window.history.replaceState({}, "", url);
  await loadCurrentProject();
});

refreshButton.addEventListener("click", loadCurrentProject);

boot().catch((error) => {
  setStatus("error", error.message);
  document.getElementById("diagnostics-list").innerHTML = `<div class="diagnostic-row">Failed to load dashboard payload: ${error.message}</div>`;
});

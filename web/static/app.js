// Visa Employer Watch: a small hash-routed front end over the JSON API in web/api.py.
// Routes: #/ (lookup), #/watchlist?filters, #/employer/<id>.
"use strict";

const app = document.getElementById("app");
const state = { back: { href: "#/", label: "Employer lookup" }, meta: null };

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const n = (x) => (x == null || x === "" ? "–" : Number(x).toLocaleString("en-US"));
const money = (x) => "$" + Math.round(Number(x || 0)).toLocaleString("en-US");
const compactMoney = (x) => {
  const v = Number(x || 0);
  if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B";
  if (v >= 1e6) return "$" + (v / 1e6).toFixed(1) + "M";
  if (v >= 1e4) return "$" + Math.round(v / 1e3) + "K";
  return money(v);
};
const day = (s) => (s ? String(s).slice(0, 10) : "–");
const titleCase = (s) => /[a-z]/.test(s || "") ? s : String(s || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
const programBadge = (p) => `<span class="badge ${p === "H-2B" ? "h2b" : "h1b"}">${esc(p)}</span>`;
const icon = {
  search: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  back: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>',
  chev: '<svg class="chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>',
  info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/></svg>',
  download: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0-4-4m4 4 4-4M4 21h16"/></svg>',
};

async function api(path, params) {
  const qs = params ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)) : "";
  const r = await fetch("/api" + path + qs);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

function loading(text = "Loading…") {
  app.innerHTML = `<div class="loading"><div class="spinner"></div>${esc(text)}</div>`;
}

function parseHash() {
  const [path, query] = location.hash.replace(/^#/, "").split("?");
  return { path: path || "/", params: new URLSearchParams(query || "") };
}

function setActiveNav(name) {
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
}

// ---------- router ----------
async function route() {
  const { path, params } = parseHash();
  const m = path.match(/^\/employer\/(\d+)$/);
  try {
    if (m) { setActiveNav((state.back.href.match(/^#\/(watchlist|map|industries)/) || [, "search"])[1]); await employerPage(+m[1]); }
    else if (path === "/watchlist") { setActiveNav("watchlist"); await watchlistPage(params); }
    else if (path === "/map") { setActiveNav("map"); await mapPage(params); }
    else if (path === "/industries") { setActiveNav("industries"); await industriesPage(params); }
    else { setActiveNav("search"); searchPage(params); }
  } catch (err) {
    app.innerHTML = `<div class="empty"><h2>Something went wrong</h2><p>${esc(err.message)}</p></div>`;
  }
}
window.addEventListener("hashchange", route);
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-employer]");
  if (a) {
    const { path } = parseHash();
    if (!path.startsWith("/employer")) {
      const labels = { "/watchlist": "Watchlist", "/map": "Map", "/industries": "Industries" };
      state.back = { href: location.hash || "#/", label: labels[path] || "Employer lookup" };
    }
  }
});

// ---------- search ----------
let searchTimer;
function searchPage(params) {
  const q = params.get("q") || "";
  app.innerHTML = `
    <section class="hero">
      <div class="eyebrow">H-1B and H-2B employers · Wage and Hour enforcement</div>
      <h1 class="page-title">Look up an employer</h1>
      <p class="lede">Search 80,950 employers that filed H-1B or H-2B applications in FY2025, and see the
        Department of Labor Wage and Hour cases linked to them. Every figure traces back to its DOL record.</p>
      <div class="searchbox">${icon.search}
        <input id="q" type="search" placeholder="Company name or trade name, e.g. Infosys" autocomplete="off" value="${esc(q)}">
      </div>
      <div class="hint-list" id="hints">
        ${["Infosys", "Cafua Management", "Cognizant", "Disney"].map((h) => `<button class="tip-hint">${h}</button>`).join("")}
      </div>
    </section>
    <div class="results" id="results"></div>`;
  const input = document.getElementById("q");
  const run = async (text) => {
    history.replaceState(null, "", text ? "#/?q=" + encodeURIComponent(text) : "#/");
    const box = document.getElementById("results");
    if (!text.trim()) { box.innerHTML = ""; return; }
    const hits = await api("/search", { q: text });
    if (input.value !== text) return; // a newer search is on its way
    box.innerHTML = hits.length ? `<div class="muted small">${hits.length === 50 ? "First 50" : hits.length} employers</div>` + hits.map((h) => `
      <a class="card result" href="#/employer/${h.employer_id}" data-employer>
        <div>
          <div class="name">${esc(h.employer_name)}${h.dba ? ` <span class="muted">· DBA ${esc(h.dba)}</span>` : ""}</div>
          <div class="where">${esc(titleCase(h.city))}, ${esc(h.state)} ${programBadge(h.program)}
            ${h.willful_violator ? '<span class="badge danger">Willful violator</span>' : ""}</div>
        </div>
        <div class="stat"><b>${n(h.n_applications)}</b>applications</div>
        <div class="stat ${h.n_cases ? "hot" : ""}"><b>${n(h.n_cases)}</b>WHD cases</div>
      </a>`).join("") : `<div class="card empty">No employers match “${esc(text)}”.</div>`;
  };
  input.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => run(input.value), 180); });
  document.getElementById("hints").addEventListener("click", (e) => {
    if (e.target.matches(".hint")) { input.value = e.target.textContent; run(input.value); }
  });
  input.focus();
  if (q) run(q);
}

// ---------- employer ----------
async function employerPage(id) {
  loading("Loading employer…");
  const d = await api("/employers/" + id);
  const e = d.employer, s = d.summary;
  const flags = [
    programBadge(e.program),
    e.willful_violator ? '<span class="badge danger"><span class="dot"></span>Willful violator (DOL)</span>' : "",
    e.h1b_dependent ? '<span class="badge warn">H-1B dependent</span>' : "",
    s.cases ? `<span class="badge danger">${n(s.cases)} WHD case${s.cases === 1 ? "" : "s"}</span>` : '<span class="badge ok">No linked WHD cases</span>',
  ].join("");
  const related = d.same_tax_id.length ? `
    <div class="related"><span class="muted small" style="align-self:center">Same tax ID elsewhere</span>
      ${d.same_tax_id.map((r) => `<a class="chip" href="#/employer/${r.employer_id}">${programBadge(r.program)}
        ${esc(r.employer_name)} · ${esc(titleCase(r.city))}, ${esc(r.state)} · ${n(r.n_applications)} apps</a>`).join("")}
    </div>` : "";

  app.innerHTML = `
    <a class="back" href="${esc(state.back.href)}">${icon.back} Back to ${esc(state.back.label)}</a>
    <section class="card emp-head">
      <div class="badges">${flags}</div>
      <h1>${esc(e.employer_name)}</h1>
      ${e.dba ? `<div class="muted">Also does business as ${esc(e.dba)}</div>` : ""}
      <div class="facts">
        <span><b>Address</b>${esc(e.address)}, ${esc(titleCase(e.city))}, ${esc(e.state)} ${esc(e.zip5)}</span>
        <span><b>Tax ID</b><span class="mono">${esc(e.fein || "not given")}</span></span>
        <span><b>NAICS</b><span class="mono">${esc(e.naics || "–")}</span>${e.sector ? ` · <a href="#/watchlist?sector=${esc(e.sector)}">${esc(e.sector_name)}</a>` : ""}</span>
      </div>
      ${related}
    </section>
    <div class="tiles">
      <div class="card tile"><div class="label">Applications</div><div class="value">${n(s.applications)}</div><div class="sub">FY2025 disclosure files</div></div>
      <div class="card tile"><div class="label">Certified</div><div class="value">${n(s.certified)}</div><div class="sub">${s.applications ? Math.round(100 * s.certified / s.applications) : 0}% of applications</div></div>
      <div class="card tile ${s.cases ? "alert" : ""}"><div class="label">Linked WHD cases</div><div class="value">${n(s.cases)}</div><div class="sub">all years, all laws</div></div>
      <div class="card tile ${s.back_wages ? "alert" : ""}"><div class="label">Back wages found</div><div class="value">${compactMoney(s.back_wages)}</div><div class="sub">${money(s.back_wages)}</div></div>
      <div class="card tile"><div class="label">Penalties assessed</div><div class="value">${compactMoney(s.penalties)}</div><div class="sub">civil money penalties</div></div>
    </div>

    ${d.case_years.length ? `<div class="card panel" style="margin-top:16px"><h3>Linked cases by year</h3>
      <div class="sub">Year the WHD findings period ended. Hover a bar for its back wages.</div>${yearColumns(d.case_years)}</div>` : ""}

    <h2 class="section">Wage and Hour cases <span class="count">${n(d.cases.length)}</span></h2>
    ${d.cases.length ? `
      <div class="callout">${icon.info}<div>WHD records carry no tax ID, so each case is linked by name and location.
        A <b style="color:var(--ok)">green</b> edge means the ZIP code matched too; <b style="color:var(--warn)">amber</b> means only the state did.
        Check the WHD name and address before relying on a link.</div></div>
      ${d.cases.map(caseCard).join("")}` : `<div class="card empty">No WHD enforcement case is linked to this employer.</div>`}

    <h2 class="section">Visa applications <span class="count" id="app-count"></span></h2>
    <div class="card" id="apps"><div class="loading"><div class="spinner"></div></div></div>
    <p class="note">Each case number is DOL's own. The source column links to the DOL disclosure file the row came from.</p>

    <details class="sources"><summary>Where this page's data comes from</summary>
      <div class="card" style="padding:16px 18px;margin-top:10px">
        <div class="source">Employer row: <span class="mono">${esc(e.source_file)}</span>
          (sha256 <span class="mono">${esc(e.source_sha256.slice(0, 12))}…</span>, built ${esc(e.source_created_utc)})<br>
          from ${e.source_urls.split(";").map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u.split("/").pop())}</a>`).join(", ")}</div>
      </div>
    </details>`;
  window.scrollTo(0, 0);
  loadApplications(id, 1);
}

function caseCard(v) {
  const zip = v.method === "clean name + ZIP";
  const bw = Number(v.bw_atp_amt || 0);
  const row = (law, cnt, wages, workers) =>
    `<tr><td>${law}</td><td class="num">${n(cnt)}</td><td class="num">${wages == null ? "" : money(wages)}</td><td class="num">${workers == null ? "" : n(workers)}</td></tr>`;
  return `
  <details class="card case">
    <summary>
      <span class="strip ${zip ? "zip" : ""}" title="${esc(v.method)}"></span>
      <div>
        <div class="title">${esc(v.trade_nm || v.legal_name || "Unnamed")}</div>
        <div class="meta">Case <span class="mono">${esc(v.case_id)}</span> · findings ${day(v.findings_start_date)} to ${day(v.findings_end_date)}
          · ${esc(titleCase(v.cty_nm))}, ${esc(v.st_cd)}
          ${v.h1b_violtn_cnt ? `<span class="badge h1b">${n(v.h1b_violtn_cnt)} H-1B</span>` : ""}
          ${v.h2b_violtn_cnt ? `<span class="badge h2b">${n(v.h2b_violtn_cnt)} H-2B</span>` : ""}</div>
      </div>
      <div class="money ${bw ? "" : "zero"}">${bw ? money(bw) : "$0"}<div class="meta">back wages</div></div>
      ${icon.chev}
    </summary>
    <div class="case-body">
      <dl class="kv">
        <dt>WHD legal name</dt><dd>${esc(v.legal_name || "–")}</dd>
        <dt>WHD trade name</dt><dd>${esc(v.trade_nm || "–")}</dd>
        <dt>WHD address</dt><dd>${esc(v.street_addr_1_txt)}, ${esc(v.cty_nm)}, ${esc(v.st_cd)} ${esc(v.zip_cd)}</dd>
        <dt>Penalties assessed</dt><dd>${money(v.cmp_assd)}</dd>
      </dl>
      <div class="table-wrap"><table class="mini">
        <thead><tr><th>Law</th><th class="num">Violations</th><th class="num">Back wages</th><th class="num">Workers</th></tr></thead>
        <tbody>
          ${row("All laws", v.case_violtn_cnt, v.bw_atp_amt || 0, v.ee_violtd_cnt)}
          ${row("H-1B", v.h1b_violtn_cnt, v.h1b_bw_atp_amt || 0, null)}
          ${row("H-2B", v.h2b_violtn_cnt, v.h2b_bw_atp_amt || 0, null)}
          ${row("H-2A", v.h2a_violtn_cnt, null, null)}
          ${row("Minimum wage / overtime (FLSA)", v.flsa_violtn_cnt, null, null)}
        </tbody></table></div>
      <div class="match"><span class="badge ${zip ? "ok" : "warn"}">${zip ? "Name + ZIP" : "Name + state"}</span>
        <div>${esc(v.match_label)}. Compared the WHD ${esc(v.whd_name_field)} with the employer ${esc(v.employer_name_field)}.</div></div>
      <div class="source">Source: WHD enforcement API <a href="${esc(v.source_urls)}" target="_blank" rel="noopener">${esc(v.source_urls)}</a>,
        case_id <span class="mono">${esc(v.case_id)}</span>, loaded by DOL ${esc(v.load_dt)} ·
        file <span class="mono">${esc(v.source_file)}</span> (sha256 <span class="mono">${esc(v.source_sha256.slice(0, 12))}…</span>)</div>
    </div>
  </details>`;
}

async function loadApplications(id, page) {
  const box = document.getElementById("apps");
  const d = await api(`/employers/${id}/applications`, { page });
  document.getElementById("app-count").textContent = n(d.total);
  const pages = Math.max(1, Math.ceil(d.total / d.page_size));
  const statusBadge = (s) => {
    const cls = /^certified$/i.test(s) ? "ok" : /withdrawn/i.test(s) ? "" : /denied/i.test(s) ? "danger" : "warn";
    return `<span class="badge ${cls}">${esc(s)}</span>`;
  };
  box.innerHTML = d.total ? `
    <div class="table-wrap"><table>
      <thead><tr><th>Case number</th><th>Status</th><th>Visa</th><th>Tax ID</th><th>DOL file</th></tr></thead>
      <tbody>${d.rows.map((a) => `<tr>
        <td class="mono">${esc(a.case_number)}</td><td>${statusBadge(a.case_status)}</td><td>${esc(a.visa_class)}</td>
        <td class="mono">${esc(a.fein)}</td>
        <td>${a.dol_file_url ? `<a href="${esc(a.dol_file_url)}" target="_blank" rel="noopener">${esc(a.source_file)}</a>` : esc(a.source_file)}</td>
      </tr>`).join("")}</tbody></table></div>
    ${pages > 1 ? `<div class="pager"><span>Page ${page} of ${n(pages)}</span><span class="btns">
      <button class="btn" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>Previous</button>
      <button class="btn" data-page="${page + 1}" ${page >= pages ? "disabled" : ""}>Next</button></span></div>` : ""}`
    : `<div class="empty">No applications.</div>`;
  box.querySelectorAll("[data-page]").forEach((b) => b.addEventListener("click", () => loadApplications(id, +b.dataset.page)));
}

// ---------- watchlist ----------
const WL_COLUMNS = [
  { key: "employer_name", label: "Employer", type: "text" },
  { key: "back_wages", label: "Back wages", type: "num" },
  { key: "n_cases", label: "Cases", type: "num" },
  { key: "visa_violations", label: "Visa violations", type: "num" },
  { key: "violations", label: "All violations", type: "num" },
  { key: "workers", label: "Workers owed", type: "num" },
  { key: "penalties", label: "Penalties", type: "num" },
  { key: "zip_share", label: "ZIP-matched", type: "num" },
  { key: "n_applications", label: "Visa apps", type: "num" },
  { key: "latest_case", label: "Latest case", type: "text" },
];
const WL_PAGE = 50;
const wl = { key: null, rows: [], sort: "back_wages", dir: -1, page: 1 };

async function watchlistPage(params) {
  if (!state.meta) state.meta = await api("/meta");
  const f = {
    program: params.get("program") || "", state: params.get("state") || "", since: params.get("since") || "",
    visa_only: params.get("visa_only") === "1", min_apps: params.get("min_apps") || "1",
    sector: params.get("sector") || "",
  };
  wl.sort = params.get("sort") || "back_wages";
  wl.dir = params.get("dir") === "asc" ? 1 : -1;
  const key = JSON.stringify(f);
  const seg = (val, label) => `<button data-program="${val}" class="${f.program === val ? "on" : ""}">${label}</button>`;
  app.innerHTML = `
    <div class="eyebrow">Ranked by enforcement history</div>
    <h1 class="page-title">Watchlist</h1>
    <p class="lede">Every H-1B and H-2B employer with Wage and Hour cases linked to it. Sort by any column,
      or open an employer to check each case and its source.</p>
    <div class="card filters">
      <div class="field"><label>Program</label><div class="segmented" id="f-program">${seg("", "All")}${seg("H-1B", "H-1B")}${seg("H-2B", "H-2B")}</div></div>
      <div class="field"><label for="f-state">State</label><select id="f-state"><option value="">All states</option>
        ${state.meta.states.map((s) => `<option ${s === f.state ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
      <div class="field"><label for="f-sector">Industry</label><select id="f-sector" style="max-width:220px"><option value="">All industries</option>
        ${Object.entries(state.meta.sectors).map(([k, v]) => `<option value="${k}" ${k === f.sector ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></div>
      <div class="field"><label for="f-since">Cases ending</label><select id="f-since">
        ${[["", "Any year"], ["2020", "2020 or later"], ["2015", "2015 or later"], ["2010", "2010 or later"], ["2005", "2005 or later"]]
          .map(([v, l]) => `<option value="${v}" ${v === f.since ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="field"><label for="f-min">Min. applications</label><input id="f-min" type="number" min="1" step="1" value="${esc(f.min_apps)}" style="width:110px"></div>
      <label class="toggle"><input id="f-visa" type="checkbox" ${f.visa_only ? "checked" : ""}> Only violations of the employer's visa program</label>
      <span class="spacer"></span>
      <button class="btn" id="csv">${icon.download} CSV</button>
    </div>
    <div class="tiles" id="wl-tiles"></div>
    <div class="card" style="margin-top:16px" id="wl-table"><div class="loading"><div class="spinner"></div>Loading watchlist…</div></div>
    <p class="note">WHD records have no tax ID, so every case is linked by name and location; “ZIP-matched” is the share linked by
      name + ZIP rather than the looser name + state. A company filing from several addresses, or in both programs, has a row for each,
      so a case can appear on more than one row. The totals above count each case once.</p>`;

  const go = (changes) => {
    const p = new URLSearchParams({ ...Object.fromEntries(params), ...changes });
    [...p.entries()].forEach(([k, v]) => { if (v === "" || (k === "min_apps" && v === "1") || (k === "visa_only" && v === "0")) p.delete(k); });
    location.hash = "#/watchlist" + (p.toString() ? "?" + p : "");
  };
  document.getElementById("f-program").addEventListener("click", (e) => { if (e.target.dataset.program != null) go({ program: e.target.dataset.program }); });
  document.getElementById("f-state").addEventListener("change", (e) => go({ state: e.target.value }));
  document.getElementById("f-since").addEventListener("change", (e) => go({ since: e.target.value }));
  document.getElementById("f-sector").addEventListener("change", (e) => go({ sector: e.target.value }));
  document.getElementById("f-min").addEventListener("change", (e) => go({ min_apps: String(Math.max(1, parseInt(e.target.value, 10) || 1)) }));
  document.getElementById("f-visa").addEventListener("change", (e) => go({ visa_only: e.target.checked ? "1" : "0" }));
  document.getElementById("csv").addEventListener("click", downloadCsv);

  if (wl.key !== key) {
    const d = await api("/watchlist", { ...f, visa_only: f.visa_only ? "true" : "" });
    wl.rows = d.rows.map((r) => ({
      ...r,
      visa_violations: r.program === "H-1B" ? r.h1b_violations : r.h2b_violations,
      zip_share: r.n_cases ? r.zip_links / r.n_cases : 0,
      latest_case: r.latest_case ? r.latest_case.slice(0, 10) : "",
    }));
    wl.totals = d.totals;
    wl.key = key;
  }
  wl.page = Math.max(1, parseInt(params.get("page"), 10) || 1);
  const t = wl.totals;
  document.getElementById("wl-tiles").innerHTML = `
    <div class="card tile"><div class="label">Employers</div><div class="value">${n(wl.rows.length)}</div></div>
    <div class="card tile"><div class="label">Linked WHD cases</div><div class="value">${n(t.cases)}</div><div class="sub">each case counted once</div></div>
    <div class="card tile alert"><div class="label">Back wages found</div><div class="value">${compactMoney(t.back_wages)}</div><div class="sub">${money(t.back_wages)}</div></div>
    <div class="card tile"><div class="label">Penalties assessed</div><div class="value">${compactMoney(t.penalties)}</div><div class="sub">${money(t.penalties)}</div></div>`;
  renderWatchlistTable(go);
}

function renderWatchlistTable(go) {
  const box = document.getElementById("wl-table");
  if (!wl.rows.length) { box.innerHTML = `<div class="empty">No employers match these filters.</div>`; return; }
  const col = WL_COLUMNS.find((c) => c.key === wl.sort) || WL_COLUMNS[1];
  const rows = [...wl.rows].sort((a, b) => {
    const x = a[col.key], y = b[col.key];
    return (col.type === "num" ? (x - y) : String(x).localeCompare(String(y))) * wl.dir || b.back_wages - a.back_wages;
  });
  const pages = Math.ceil(rows.length / WL_PAGE);
  const page = Math.min(wl.page, pages);
  const shown = rows.slice((page - 1) * WL_PAGE, page * WL_PAGE);
  const maxBw = Math.max(...wl.rows.map((r) => r.back_wages), 1);
  const th = (c) => `<th data-sort="${c.key}" class="${c.type === "num" ? "num" : ""} ${c.key === col.key ? "sorted" : ""}">${c.label}<span class="arrow">${c.key === col.key ? (wl.dir < 0 ? "↓" : "↑") : "↕"}</span></th>`;
  box.innerHTML = `
    <div class="table-wrap" style="max-height:70vh"><table class="sortable clickable">
      <thead><tr>${WL_COLUMNS.map(th).join("")}</tr></thead>
      <tbody>${shown.map((r) => `<tr data-id="${r.employer_id}">
        <td><a class="emp" href="#/employer/${r.employer_id}" data-employer title="${esc(r.employer_name)}">${esc(r.employer_name)}</a>
          <div class="emp-sub">${programBadge(r.program)} ${esc(titleCase(r.city))}, ${esc(r.state)}${r.willful_violator ? ' · <span style="color:var(--danger)">willful violator</span>' : ""}</div></td>
        <td class="num"><span class="bar"><i style="width:${Math.max(2, 100 * r.back_wages / maxBw)}%"></i><span>${money(r.back_wages)}</span></span></td>
        <td class="num">${n(r.n_cases)}</td>
        <td class="num">${r.visa_violations ? `<b>${n(r.visa_violations)}</b>` : '<span class="muted">0</span>'}</td>
        <td class="num">${n(r.violations)}</td>
        <td class="num">${n(r.workers)}</td>
        <td class="num">${money(r.penalties)}</td>
        <td class="num"><span class="badge ${r.zip_share === 1 ? "ok" : r.zip_share === 0 ? "warn" : ""}">${r.zip_links} of ${r.n_cases}</span></td>
        <td class="num">${n(r.n_applications)}</td>
        <td class="mono small">${esc(r.latest_case || "–")}</td>
      </tr>`).join("")}</tbody></table></div>
    <div class="pager"><span>${n((page - 1) * WL_PAGE + 1)}–${n(Math.min(page * WL_PAGE, rows.length))} of ${n(rows.length)} employers</span>
      <span class="btns"><button class="btn" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>Previous</button>
      <button class="btn" data-page="${page + 1}" ${page >= pages ? "disabled" : ""}>Next</button></span></div>`;
  box.querySelectorAll("th[data-sort]").forEach((h) => h.addEventListener("click", () => {
    const k = h.dataset.sort, c = WL_COLUMNS.find((x) => x.key === k);
    const dir = k === wl.sort ? (wl.dir < 0 ? "asc" : "desc") : (c.type === "num" ? "desc" : "asc");
    go({ sort: k, dir, page: "" });
  }));
  box.querySelectorAll("[data-page]").forEach((b) => b.addEventListener("click", () => go({ page: b.dataset.page })));
  box.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    state.back = { href: location.hash, label: "Watchlist" };
    location.hash = "#/employer/" + tr.dataset.id;
  }));
}

function downloadCsv() {
  const cols = ["employer_id", "employer_name", "city", "state", "program", "n_applications", "n_cases", "zip_links",
    "visa_violations", "violations", "back_wages", "workers", "penalties", "latest_case", "willful_violator"];
  const cell = (v) => /[",\n]/.test(String(v ?? "")) ? `"${String(v).replace(/"/g, '""')}"` : String(v ?? "");
  const csv = [cols.join(",")].concat(wl.rows.map((r) => cols.map((c) => cell(r[c])).join(","))).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "watchlist.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---------- shared chart helpers ----------
const tip = document.getElementById("tooltip");
function showTip(html, ev) {
  tip.innerHTML = html;
  tip.classList.add("on");
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + w > innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > innerHeight - 8) y = ev.clientY - h - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
function hideTip() { tip.classList.remove("on"); }
window.addEventListener("hashchange", hideTip);
const tipRows = (pairs) => pairs.map(([k, v]) => `<div class="row"><span>${esc(k)}</span><span>${v}</span></div>`).join("");
function bindTips(root, html) {
  root.querySelectorAll("[data-tip]").forEach((el) => {
    el.addEventListener("mousemove", (ev) => showTip(html(el.dataset.tip), ev));
    el.addEventListener("mouseleave", hideTip);
  });
}
const pct = (x, digits = 1) => (100 * x).toFixed(digits) + "%";
const niceMax = (v) => {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v))), m = v / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
};

function yearColumns(years) {
  const first = years[0].year, last = Math.max(years[years.length - 1].year, first);
  const all = [];
  for (let y = first; y <= last; y++) all.push(years.find((r) => r.year === y) || { year: y, cases: 0, back_wages: 0 });
  const W = 1100, H = 190, L = 34, B = 22, T = 8, max = niceMax(Math.max(...all.map((r) => r.cases)));
  const bw = (W - L) / all.length, gap = Math.min(6, bw * 0.25);
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const ticks = [0, max / 2, max];
  const labelEvery = Math.ceil(all.length / 14);
  return `<svg class="columns" viewBox="0 0 ${W} ${H}" role="img" aria-label="Linked WHD cases per year">
    ${ticks.map((t) => `<line class="gridline" x1="${L}" x2="${W}" y1="${y(t)}" y2="${y(t)}"/><text class="axis" x="${L - 6}" y="${y(t) + 4}" text-anchor="end">${n(t)}</text>`).join("")}
    ${all.map((r, i) => r.cases ? `<path class="bar" data-tip="${i}" d="${roundTop(L + i * bw + gap / 2, y(r.cases), bw - gap, y(0) - y(r.cases), 4)}"/>` : "").join("")}
    ${all.map((r, i) => i % labelEvery === 0 ? `<text class="axis" x="${L + i * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${r.year}</text>` : "").join("")}
  </svg>`.replace("<svg", `<svg data-years='${esc(JSON.stringify(all))}'`);
}
function roundTop(x, y, w, h, r) {
  r = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
// Column-chart tooltips are bound after the employer page renders.
new MutationObserver(() => {
  document.querySelectorAll("svg.columns[data-years]:not([data-bound])").forEach((svg) => {
    svg.dataset.bound = "1";
    const all = JSON.parse(svg.dataset.years);
    bindTips(svg, (i) => `<b>${all[i].year}</b>` + tipRows([["Cases", n(all[i].cases)], ["Back wages", money(all[i].back_wages)]]));
  });
}).observe(app, { childList: true, subtree: true });

// ---------- map ----------
const TILES = {
  AK: [0, 0], ME: [11, 0], WI: [6, 1], VT: [10, 1], NH: [11, 1],
  WA: [1, 2], ID: [2, 2], MT: [3, 2], ND: [4, 2], MN: [5, 2], IL: [6, 2], MI: [7, 2], NY: [9, 2], MA: [10, 2],
  OR: [1, 3], NV: [2, 3], WY: [3, 3], SD: [4, 3], IA: [5, 3], IN: [6, 3], OH: [7, 3], PA: [8, 3], NJ: [9, 3], CT: [10, 3], RI: [11, 3],
  CA: [1, 4], UT: [2, 4], CO: [3, 4], NE: [4, 4], MO: [5, 4], KY: [6, 4], WV: [7, 4], VA: [8, 4], MD: [9, 4], DE: [10, 4],
  AZ: [2, 5], NM: [3, 5], KS: [4, 5], AR: [5, 5], TN: [6, 5], NC: [7, 5], SC: [8, 5], DC: [9, 5],
  OK: [4, 6], LA: [5, 6], MS: [6, 6], AL: [7, 6], GA: [8, 6],
  HI: [0, 7], TX: [4, 7], FL: [9, 7], PR: [11, 7],
};
const MIN_EMPLOYERS = 30;
const METRICS = {
  cases_per_100: { label: "Cases per 100 visa employers", fmt: (v) => v.toFixed(1), rate: true,
    note: "Linked WHD cases for every 100 visa employers in the state. Fairer than raw counts, because big states have more of everything." },
  share_with_cases: { label: "Share of employers with a case", fmt: (v) => pct(v), rate: true,
    note: "The share of the state's visa employers that have at least one linked WHD case." },
  back_wages: { label: "Back wages", fmt: (v) => compactMoney(v), rate: false,
    note: "Back wages found in the linked WHD cases, each case counted once." },
  cases: { label: "Linked cases", fmt: (v) => n(v), rate: false,
    note: "Number of WHD cases linked to the state's visa employers, each counted once." },
};
const STATE_NAMES = { AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware", DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York", NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming", PR: "Puerto Rico", GU: "Guam", VI: "U.S. Virgin Islands", MP: "Northern Mariana Islands", AS: "American Samoa" };

function groupFilters(params, base) {
  const program = params.get("program") || "", visa = params.get("visa_only") === "1";
  const go = (changes) => {
    const p = new URLSearchParams({ ...Object.fromEntries(params), ...changes });
    [...p.entries()].forEach(([k, v]) => { if (v === "" || (k === "visa_only" && v === "0")) p.delete(k); });
    location.hash = base + (p.toString() ? "?" + p : "");
  };
  const seg = (val, label) => `<button data-program="${val}" class="${program === val ? "on" : ""}">${label}</button>`;
  const html = `
      <div class="field"><label>Program</label><div class="segmented" id="g-program">${seg("", "All")}${seg("H-1B", "H-1B")}${seg("H-2B", "H-2B")}</div></div>
      <label class="toggle"><input id="g-visa" type="checkbox" ${visa ? "checked" : ""}> Only violations of the employer's visa program</label>`;
  const bind = () => {
    document.getElementById("g-program").addEventListener("click", (e) => { if (e.target.dataset.program != null) go({ program: e.target.dataset.program }); });
    document.getElementById("g-visa").addEventListener("change", (e) => go({ visa_only: e.target.checked ? "1" : "0" }));
  };
  const toWatchlist = (extra) => {
    const p = new URLSearchParams({ ...(program ? { program } : {}), ...(visa ? { visa_only: "1" } : {}), ...extra });
    return "#/watchlist?" + p;
  };
  return { program, visa, go, html, bind, toWatchlist };
}

// Quantile class breaks over the states that have enough employers to be meaningful.
function quantileBreaks(values, k = 7) {
  const v = [...values].sort((a, b) => a - b);
  if (!v.length) return [];
  return Array.from({ length: k - 1 }, (_, i) => v[Math.min(v.length - 1, Math.floor(((i + 1) * v.length) / k))]);
}
const classOf = (v, breaks) => 1 + breaks.filter((b) => v >= b).length;

async function mapPage(params) {
  loading("Loading map…");
  const g = groupFilters(params, "#/map");
  const metric = METRICS[params.get("metric")] ? params.get("metric") : "cases_per_100";
  const M = METRICS[metric];
  const data = await api("/states", { program: g.program, visa_only: g.visa ? "true" : "" });
  const byState = Object.fromEntries(data.map((r) => [r.state, r]));
  const enough = (r) => r && (!M.rate || r.employers >= MIN_EMPLOYERS);
  const rated = data.filter((r) => TILES[r.state] && enough(r));
  const breaks = quantileBreaks(rated.map((r) => r[metric]));
  const total = data.reduce((a, r) => ({ e: a.e + r.employers, c: a.c + r.cases, w: a.w + r.back_wages, x: a.x + r.employers_with_cases }), { e: 0, c: 0, w: 0, x: 0 });
  const S = 64, G = 4;
  const tiles = Object.entries(TILES).map(([st, [c, r]]) => {
    const d = byState[st];
    const ok = enough(d);
    const cls = ok ? classOf(d[metric], breaks) : 0;
    const dark = cls >= 5;
    return `<a class="st ${ok ? "" : "na"}" href="${g.toWatchlist({ state: st })}" data-tip="${st}" aria-label="${esc(STATE_NAMES[st] || st)}">
      <rect x="${c * (S + G)}" y="${r * (S + G)}" width="${S}" height="${S}" style="fill:var(--seq-${cls})"/>
      <text x="${c * (S + G) + S / 2}" y="${r * (S + G) + S / 2 - 2}" text-anchor="middle" style="fill:${dark ? "#fff" : "var(--ink)"}">${st}</text>
      <text class="val" x="${c * (S + G) + S / 2}" y="${r * (S + G) + S / 2 + 13}" text-anchor="middle" style="fill:${dark ? "rgba(255,255,255,.85)" : "var(--ink-2)"}">${ok ? M.fmt(d[metric]) : d ? "few" : "–"}</text>
    </a>`;
  }).join("");
  const W = 12 * (S + G), H = 8 * (S + G);
  const ranked = [...rated].sort((a, b) => b[metric] - a[metric]);
  const top = ranked.slice(0, 12), maxV = top.length ? top[0][metric] : 1;
  const others = data.filter((r) => !TILES[r.state]).map((r) => r.state);
  const lo = (i) => (i === 0 ? (rated.length ? Math.min(...rated.map((r) => r[metric])) : 0) : breaks[i - 1]);

  app.innerHTML = `
    <div class="eyebrow">Where enforcement history concentrates</div>
    <h1 class="page-title">Map</h1>
    <p class="lede">Each square is a state, colored by how much Wage and Hour enforcement is linked to its H-1B and H-2B employers.
      Hover for details, or click a state to open its employers in the Watchlist.</p>
    <div class="card filters">
      <div class="field"><label for="m-metric">Color states by</label><select id="m-metric">
        ${Object.entries(METRICS).map(([k, v]) => `<option value="${k}" ${k === metric ? "selected" : ""}>${v.label}</option>`).join("")}</select></div>
      ${g.html}
    </div>
    <div class="tiles">
      <div class="card tile"><div class="label">Visa employers</div><div class="value">${n(total.e)}</div><div class="sub">${n(total.x)} with a linked case</div></div>
      <div class="card tile"><div class="label">Cases per 100 employers</div><div class="value">${total.e ? (100 * total.c / total.e).toFixed(1) : "0"}</div><div class="sub">national rate</div></div>
      <div class="card tile alert"><div class="label">Back wages found</div><div class="value">${compactMoney(total.w)}</div><div class="sub">${money(total.w)}</div></div>
      <div class="card tile"><div class="label">Highest state</div><div class="value">${ranked[0] ? esc(ranked[0].state) : "–"}</div><div class="sub">${ranked[0] ? esc(M.label.toLowerCase()) + ": " + M.fmt(ranked[0][metric]) : ""}</div></div>
    </div>
    <div class="grid-2">
      <div class="card panel">
        <h3>${esc(M.label)} by state</h3>
        <div class="sub">${esc(M.note)}</div>
        <svg class="tilemap" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(M.label)} by state">${tiles}</svg>
        <div class="legend">
          <div><div class="ramp">${[1, 2, 3, 4, 5, 6, 7].map((i) => `<span style="background:var(--seq-${i})" title="${M.fmt(lo(i - 1))} and up"></span>`).join("")}</div>
            <div class="ramp-labels"><span>${rated.length ? M.fmt(lo(0)) : ""}</span><span>${rated.length ? M.fmt(Math.max(...rated.map((r) => r[metric]))) : ""}</span></div></div>
          <span><span class="swatch" style="background:var(--seq-0)"></span>${M.rate ? `Fewer than ${MIN_EMPLOYERS} visa employers` : "No visa employers"}</span>
          <span>Seven equal-count groups: each shade holds about the same number of states.</span>
        </div>
        ${others.length ? `<div class="note">Also in the data: ${others.map((s) => `<a href="${g.toWatchlist({ state: s })}">${esc(STATE_NAMES[s] || s)}</a>`).join(", ")}.</div>` : ""}
      </div>
      <div class="card panel">
        <h3>Top states</h3>
        <div class="sub">${esc(M.label)}${M.rate ? `, states with ${MIN_EMPLOYERS}+ visa employers` : ""}</div>
        <div class="rank">${top.map((r) => `
          <a class="rank-row" href="${g.toWatchlist({ state: r.state })}" data-tip="${r.state}">
            <b>${esc(r.state)}</b><div class="track"><div class="fill" style="width:${Math.max(1.5, 100 * r[metric] / maxV)}%"></div></div>
            <span class="v">${M.fmt(r[metric])}</span></a>`).join("")}</div>
      </div>
    </div>
    <details class="sources"><summary>Show all states as a table</summary>
      <div class="card" style="margin-top:10px"><div class="table-wrap"><table>
        <thead><tr><th>State</th><th class="num">Visa employers</th><th class="num">With a case</th><th class="num">Share</th><th class="num">Cases</th><th class="num">Per 100</th><th class="num">Back wages</th><th class="num">Penalties</th></tr></thead>
        <tbody>${[...data].sort((a, b) => b.cases - a.cases).map((r) => `<tr>
          <td><a href="${g.toWatchlist({ state: r.state })}">${esc(STATE_NAMES[r.state] || r.state)}</a></td><td class="num">${n(r.employers)}</td>
          <td class="num">${n(r.employers_with_cases)}</td><td class="num">${pct(r.share_with_cases)}</td><td class="num">${n(r.cases)}</td>
          <td class="num">${r.cases_per_100.toFixed(1)}</td><td class="num">${money(r.back_wages)}</td><td class="num">${money(r.penalties)}</td></tr>`).join("")}</tbody>
      </table></div></div>
    </details>
    <p class="note">A case counts toward a state when it is linked to a visa employer there. WHD cases have no tax ID, so links are by name and location; see each employer's page for how each case was linked.</p>`;
  g.bind();
  document.getElementById("m-metric").addEventListener("change", (e) => g.go({ metric: e.target.value }));
  bindTips(app, (st) => {
    const d = byState[st];
    if (!d) return `<b>${esc(STATE_NAMES[st] || st)}</b><div class="tip-hint">No visa employers in the data.</div>`;
    return `<b>${esc(STATE_NAMES[st] || st)}</b>` + tipRows([
      ["Visa employers", n(d.employers)], ["With a linked case", `${n(d.employers_with_cases)} (${pct(d.share_with_cases)})`],
      ["Linked cases", n(d.cases)], ["Cases per 100", d.cases_per_100.toFixed(1)], ["Back wages", money(d.back_wages)],
      ["Visa-program violations", n(d.visa_violations)],
    ]) + (enough(d) ? "" : `<div class="tip-hint">Fewer than ${MIN_EMPLOYERS} visa employers, so not shaded.</div>`) + `<div class="tip-hint">Click to see these employers</div>`;
  });
}

// Direct labels beside dots: right of the dot unless that runs off the chart, and skipped if they would overlap one already placed.
// Labels for scatter dots: each tries right, left, above, below and skips any
// spot that would cover another label or any dot in `obstacles`.
function placeLabels(items, right, obstacles = []) {
  const placed = obstacles.map((o) => [o.x - o.r, o.y - o.r, 2 * o.r, 2 * o.r]), out = [];
  for (const it of items.sort((a, b) => b.r - a.r)) {
    const w = it.text.length * 6.6, h = 14;
    const candidates = [
      { x: it.x + it.r + 5, y: it.y + 4, anchor: "start", box: [it.x + it.r + 5, it.y - 8, w, h] },
      { x: it.x - it.r - 5, y: it.y + 4, anchor: "end", box: [it.x - it.r - 5 - w, it.y - 8, w, h] },
      { x: it.x, y: it.y - it.r - 6, anchor: "middle", box: [it.x - w / 2, it.y - it.r - 18, w, h] },
      { x: it.x, y: it.y + it.r + 14, anchor: "middle", box: [it.x - w / 2, it.y + it.r + 2, w, h] },
    ];
    const hit = (a, b) => a[0] < b[0] + b[2] && b[0] < a[0] + a[2] && a[1] < b[1] + b[3] && b[1] < a[1] + a[3];
    const own = [it.x - it.r, it.y - it.r, 2 * it.r, 2 * it.r];
    const c = candidates.find((c) => c.box[0] >= 0 && c.box[0] + c.box[2] <= right
      && !placed.some((p) => !(p[0] === own[0] && p[1] === own[1] && p[2] === own[2]) && hit(p, c.box)));
    if (!c) continue;
    placed.push(c.box);
    out.push(`<text class="lbl" x="${c.x}" y="${c.y}" text-anchor="${c.anchor}">${esc(it.text)}</text>`);
  }
  return out.join("");
}

// ---------- industries ----------
async function industriesPage(params) {
  loading("Loading industries…");
  const g = groupFilters(params, "#/industries");
  const data = (await api("/sectors", { program: g.program, visa_only: g.visa ? "true" : "" })).filter((r) => r.employers > 0);
  const bySector = Object.fromEntries(data.map((r) => [r.sector, r]));
  const totE = data.reduce((a, r) => a + r.employers, 0), totX = data.reduce((a, r) => a + r.employers_with_cases, 0);
  const avgShare = totE ? totX / totE : 0;
  const shareRank = [...data].sort((a, b) => b.share_with_cases - a.share_with_cases);
  const wageRank = [...data].sort((a, b) => b.back_wages - a.back_wages);
  const maxShare = niceMax(Math.max(...data.map((r) => r.share_with_cases), 0.01));
  const maxWage = Math.max(...data.map((r) => r.back_wages), 1);
  const hbar = (r, value, max, label, extra = "") => `
    <a class="hbar" href="${g.toWatchlist({ sector: r.sector })}" data-tip="${r.sector}">
      <span class="name" title="${esc(r.name)}">${esc(r.name)}</span>
      <span class="track"><span class="fill" style="width:${Math.max(0.8, 100 * value / max)}%"></span>${extra}</span>
      <span class="v">${label}</span></a>`;

  // Scatter: how many visa employers a sector has (log x) against the share with a case (y).
  const W = 1100, H = 440, L = 52, R = 30, T = 28, B = 48;
  const xs = data.map((r) => r.employers), x0 = Math.log10(Math.max(1, Math.min(...xs)) / 1.5), x1 = Math.log10(Math.max(...xs) * 1.5);
  const sx = (v) => L + (W - L - R) * (Math.log10(v) - x0) / (x1 - x0);
  const sy = (v) => T + (H - T - B) * (1 - v / maxShare);
  const maxBw = Math.max(...data.map((r) => r.back_wages), 1);
  const rad = (bw) => 5 + 19 * Math.sqrt(bw / maxBw);
  const xticks = [100, 300, 1000, 3000, 10000, 30000].filter((t) => Math.log10(t) >= x0 && Math.log10(t) <= x1);
  const yticks = [0, maxShare / 4, maxShare / 2, (3 * maxShare) / 4, maxShare];
  const labelled = new Set([...shareRank.slice(0, 4), ...[...data].sort((a, b) => b.employers - a.employers).slice(0, 3)].map((r) => r.sector));
  const short = (name) => name.split(/[,(]/)[0];
  const scatter = `<svg class="scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="Visa employers against share with a WHD case, by industry">
    ${yticks.map((t) => `<line class="gridline" x1="${L}" x2="${W - R}" y1="${sy(t)}" y2="${sy(t)}"/><text class="axis" x="${L - 8}" y="${sy(t) + 4}" text-anchor="end">${pct(t, 0)}</text>`).join("")}
    ${xticks.map((t) => `<text class="axis" x="${sx(t)}" y="${H - B + 18}" text-anchor="middle">${n(t)}</text>`).join("")}
    <line x1="${L}" x2="${W - R}" y1="${sy(avgShare)}" y2="${sy(avgShare)}" stroke="var(--ink-3)" stroke-dasharray="4 4"/>
    <text class="axis" x="${W - R}" y="${sy(avgShare) - 6}" text-anchor="end">all industries ${pct(avgShare)}</text>
    <text class="axis" x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">Visa employers in the industry (log scale) →</text>
    ${[...data].sort((a, b) => b.back_wages - a.back_wages).map((r) => `<circle class="dot" data-tip="${r.sector}" cx="${sx(r.employers)}" cy="${sy(r.share_with_cases)}" r="${rad(r.back_wages)}"/>`).join("")}
    ${placeLabels(data.filter((r) => labelled.has(r.sector)).map((r) => ({ text: short(r.name), x: sx(r.employers), y: sy(r.share_with_cases), r: rad(r.back_wages) })), W - R, data.map((r) => ({ x: sx(r.employers), y: sy(r.share_with_cases), r: rad(r.back_wages) })))}
  </svg>`;

  app.innerHTML = `
    <div class="eyebrow">Enforcement history by industry</div>
    <h1 class="page-title">Industries</h1>
    <p class="lede">Visa employers grouped by industry (the first two digits of their NAICS code). Which industries have the most
      employers with Wage and Hour cases, and where the back wages are. Click any industry to open its employers in the Watchlist.</p>
    <div class="card filters">${g.html}</div>
    <div class="tiles">
      <div class="card tile"><div class="label">Industries</div><div class="value">${n(data.length)}</div><div class="sub">NAICS sectors</div></div>
      <div class="card tile"><div class="label">Share of employers with a case</div><div class="value">${pct(avgShare)}</div><div class="sub">across all industries</div></div>
      <div class="card tile alert"><div class="label">Highest share</div><div class="value">${shareRank[0] ? pct(shareRank[0].share_with_cases) : "–"}</div><div class="sub">${shareRank[0] ? esc(shareRank[0].name) : ""}</div></div>
      <div class="card tile"><div class="label">Most back wages</div><div class="value">${wageRank[0] ? compactMoney(wageRank[0].back_wages) : "–"}</div><div class="sub">${wageRank[0] ? esc(wageRank[0].name) : ""}</div></div>
    </div>
    <div class="card panel" style="margin-top:16px">
      <h3>Size against enforcement rate</h3>
      <div class="sub">Each circle is an industry: further right means more visa employers, higher means a larger share of them have a linked
        WHD case, and a bigger circle means more back wages. The dashed line is the rate across all industries.</div>
      ${scatter}
    </div>
    <div class="grid-2 even">
      <div class="card panel">
        <h3>Share of visa employers with a linked case</h3>
        <div class="sub">Dashed line: all industries (${pct(avgShare)})</div>
        <div class="hbars">${shareRank.map((r) => hbar(r, r.share_with_cases, maxShare, pct(r.share_with_cases),
          `<span class="avg-mark" style="left:${100 * avgShare / maxShare}%"></span>`)).join("")}</div>
      </div>
      <div class="card panel">
        <h3>Back wages found</h3>
        <div class="sub">In linked WHD cases, each case counted once per industry</div>
        <div class="hbars">${wageRank.map((r) => hbar(r, r.back_wages, maxWage, compactMoney(r.back_wages))).join("")}</div>
      </div>
    </div>
    <details class="sources"><summary>Show all industries as a table</summary>
      <div class="card" style="margin-top:10px"><div class="table-wrap"><table>
        <thead><tr><th>Industry</th><th>NAICS</th><th class="num">Visa employers</th><th class="num">Applications</th><th class="num">With a case</th><th class="num">Share</th><th class="num">Cases</th><th class="num">Back wages</th><th class="num">Penalties</th></tr></thead>
        <tbody>${data.map((r) => `<tr><td><a href="${g.toWatchlist({ sector: r.sector })}">${esc(r.name)}</a></td><td class="mono">${esc(r.sector)}</td>
          <td class="num">${n(r.employers)}</td><td class="num">${n(r.applications)}</td><td class="num">${n(r.employers_with_cases)}</td>
          <td class="num">${pct(r.share_with_cases)}</td><td class="num">${n(r.cases)}</td><td class="num">${money(r.back_wages)}</td><td class="num">${money(r.penalties)}</td></tr>`).join("")}</tbody>
      </table></div></div>
    </details>
    <p class="note">Industry comes from the NAICS code the employer gave on its visa applications. Employers with a missing or malformed code are left out.
      WHD cases are linked by name and location; see each employer's page for how each case was linked.</p>`;
  g.bind();
  bindTips(app, (sec) => {
    const d = bySector[sec];
    return `<b>${esc(d.name)}</b>` + tipRows([
      ["Visa employers", n(d.employers)], ["Applications", n(d.applications)],
      ["With a linked case", `${n(d.employers_with_cases)} (${pct(d.share_with_cases)})`], ["Linked cases", n(d.cases)],
      ["Back wages", money(d.back_wages)], ["Penalties", money(d.penalties)], ["Visa-program violations", n(d.visa_violations)],
    ]) + `<div class="tip-hint">Click to see these employers</div>`;
  });
}

route();

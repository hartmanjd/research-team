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
    if (m) { setActiveNav(state.back.href.startsWith("#/watchlist") ? "watchlist" : "search"); await employerPage(+m[1]); }
    else if (path === "/watchlist") { setActiveNav("watchlist"); await watchlistPage(params); }
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
      state.back = { href: location.hash || "#/", label: path === "/watchlist" ? "Watchlist" : "Employer lookup" };
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
        ${["Infosys", "Cafua Management", "Cognizant", "Disney"].map((h) => `<button class="hint">${h}</button>`).join("")}
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
        <span><b>NAICS</b><span class="mono">${esc(e.naics || "–")}</span></span>
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

route();

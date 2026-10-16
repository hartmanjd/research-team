"""Read-only lookups on research.db for the dashboard.

Plain functions over a sqlite3 connection, returning lists of dicts, so they can
be tested without Streamlit. See h1b-data/README.md for the tables.
"""
import gzip, hashlib, os, shutil, sqlite3, sys, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "h1b-data", "scripts"))
from employer_keys import clean_name  # noqa: E402

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "h1b-data", "research.db")

# A gzipped copy of research.db published as a GitHub release asset, for hosts (like Streamlit
# Cloud) that only have the git checkout. The checksum is of the .gz file at that URL.
DB_URL = "https://github.com/hartmanjd/research-team/releases/download/data-2026-10-15/research.db.gz"
DB_SHA256 = "02e7ff6c96e2ac4cd8194bb8f9db7d581dd096e59c42a74f174126e50b931c67"


def connect(path=None):
    """Open the database read-only (mode=ro), so the dashboard can never change it."""
    path = os.path.abspath(path or os.environ.get("RESEARCH_DB") or DEFAULT_DB)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No database at {path}; build it with h1b-data/scripts/build_db.py "
                                "or set RESEARCH_DB")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def download_db(path=None, url=None, sha256=None):
    """Download the gzipped database to `path` if it is not there yet, and return the path.

    The download is checked against its SHA-256 before it is unpacked, and written under a
    temporary name first, so a failed or wrong download never leaves a database behind.
    """
    path = os.path.abspath(path or os.environ.get("RESEARCH_DB") or DEFAULT_DB)
    if os.path.exists(path):
        return path
    url = url or os.environ.get("RESEARCH_DB_URL") or DB_URL
    sha256 = sha256 or os.environ.get("RESEARCH_DB_SHA256") or DB_SHA256
    gz, part = path + ".gz.part", path + ".part"
    try:
        digest = hashlib.sha256()
        with urllib.request.urlopen(url) as r, open(gz, "wb") as f:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                digest.update(chunk)
                f.write(chunk)
        if digest.hexdigest() != sha256:
            raise ValueError(f"Downloaded database from {url} has checksum {digest.hexdigest()}, "
                             f"expected {sha256}")
        with gzip.open(gz, "rb") as src, open(part, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        os.replace(part, path)
    finally:
        for tmp in (gz, part):
            if os.path.exists(tmp):
                os.remove(tmp)
    return path


def rows(con, sql, *args):
    return [dict(r) for r in con.execute(sql, args)]


def search_employers(con, text, limit=50):
    """Employers whose name or DBA contains the search text, after the same cleaning as matching.

    Ranked by exact name first, then by number of applications.
    """
    key = clean_name(text)
    if not key:
        return []
    like = f"%{key}%"
    return rows(con, """
        SELECT e.employer_id, e.program, e.employer_name, e.dba, e.city, e.state, e.fein,
               e.n_applications, e.willful_violator,
               (SELECT COUNT(*) FROM matches m WHERE m.employer_id = e.employer_id) AS n_cases
        FROM employers e
        WHERE e.name_clean LIKE ? OR e.dba_clean LIKE ?
        ORDER BY (e.name_clean = ?) DESC, e.n_applications DESC
        LIMIT ?""", like, like, key, limit)


def employer(con, employer_id):
    r = rows(con, """
        SELECT e.*, s.file AS source_file, s.sha256 AS source_sha256, s.urls AS source_urls,
               s.created_utc AS source_created_utc
        FROM employers e JOIN sources s USING (source_id) WHERE e.employer_id = ?""", employer_id)
    return r[0] if r else None


def same_tax_id(con, employer_id):
    """Other employer rows (other program, or another address) sharing a tax ID with this one."""
    emp = employer(con, employer_id)
    feins = [f for f in (emp or {}).get("fein", "").split(";") if f]
    if not feins:
        return []
    found = {}
    for f in feins:
        for r in rows(con, """
                SELECT employer_id, program, employer_name, city, state, fein, n_applications
                FROM employers WHERE employer_id != ? AND (';' || fein || ';') LIKE ?""",
                      employer_id, f"%;{f};%"):
            found[r["employer_id"]] = r
    return sorted(found.values(), key=lambda r: (r["program"], -r["n_applications"]))


def summary(con, employer_id):
    """Headline numbers: applications and the WHD cases linked to this employer."""
    return rows(con, """
        SELECT (SELECT n_applications FROM employers WHERE employer_id = ?) AS applications,
               (SELECT n_certified FROM employers WHERE employer_id = ?) AS certified,
               COUNT(v.case_id) AS cases,
               COALESCE(SUM(v.bw_atp_amt), 0) AS back_wages,
               COALESCE(SUM(v.cmp_assd), 0) AS penalties,
               COALESCE(SUM(v.h1b_violtn_cnt), 0) AS h1b_violations,
               COALESCE(SUM(v.h2b_violtn_cnt), 0) AS h2b_violations
        FROM matches m JOIN violation_cases v USING (case_id)
        WHERE m.employer_id = ?""", employer_id, employer_id, employer_id)[0]


def cases(con, employer_id):
    """WHD cases linked to this employer, newest first, with how each link was made."""
    return rows(con, """
        SELECT v.case_id, v.trade_nm, v.legal_name, v.street_addr_1_txt, v.cty_nm, v.st_cd, v.zip_cd,
               v.findings_start_date, v.findings_end_date, v.case_violtn_cnt, v.bw_atp_amt,
               v.ee_violtd_cnt, v.cmp_assd, v.h1b_violtn_cnt, v.h1b_bw_atp_amt, v.h2b_violtn_cnt,
               v.h2b_bw_atp_amt, v.h2a_violtn_cnt, v.flsa_violtn_cnt, v.load_dt,
               m.method, m.est_false_match_rate, m.whd_name_field, m.employer_name_field,
               s.file AS source_file, s.sha256 AS source_sha256, s.urls AS source_urls
        FROM matches m JOIN violation_cases v USING (case_id) JOIN sources s ON s.source_id = v.source_id
        WHERE m.employer_id = ?
        ORDER BY v.findings_end_date DESC, v.case_id DESC""", employer_id)


def applications(con, employer_id, limit=None):
    """Visa applications filed by this employer, with the DOL file each came from."""
    sql = """
        SELECT a.case_number, a.case_status, a.visa_class, a.fein, a.source_file,
               s.file AS table_file, s.sha256 AS table_sha256, s.urls AS table_urls
        FROM applications a JOIN sources s USING (source_id)
        WHERE a.employer_id = ? ORDER BY a.case_number"""
    out = rows(con, sql + " LIMIT ?", employer_id, limit) if limit else rows(con, sql, employer_id)
    for r in out:
        r["dol_file_url"] = dol_file_url(r["source_file"], r.pop("table_urls"))
    return out


def dol_file_url(csv_name, urls):
    """The DOL workbook a converted CSV came from, e.g. LCA_..._Q1.csv -> .../LCA_..._Q1.xlsx."""
    stem = os.path.splitext(csv_name or "")[0]
    for u in (urls or "").split(";"):
        if stem and os.path.splitext(u.rsplit("/", 1)[-1])[0] == stem:
            return u
    return ""


def _watchlist_filter(program, since_year, visa_violations_only, min_applications, state, sector=None):
    where, args = ["e.n_applications >= ?"], [min_applications]
    if sector:
        prefixes = SECTOR_PREFIXES.get(sector)
        if prefixes is None:
            raise ValueError(f"Unknown NAICS sector {sector!r}")
        where.append("(" + " OR ".join("e.naics LIKE ?" for _ in prefixes) + ")")
        args += [f"{p}%" for p in prefixes]
    if program:
        where.append("e.program = ?")
        args.append(program)
    if state:
        where.append("e.state = ?")
        args.append(state)
    if since_year:
        where.append("v.findings_end_date >= ?")
        args.append(f"{int(since_year):04d}")
    if visa_violations_only:
        where.append("CASE e.program WHEN 'H-1B' THEN v.h1b_violtn_cnt WHEN 'H-2B' THEN v.h2b_violtn_cnt END > 0")
    return " AND ".join(where), args


def watchlist(con, program=None, since_year=None, visa_violations_only=False, min_applications=1,
              state=None, sector=None):
    """Visa employers with linked WHD cases, one row per employer, most back wages first.

    `since_year` keeps cases whose findings end in or after that year. `visa_violations_only` keeps
    cases with violations under the employer's own visa program (H-1B or H-2B). Cases with no
    findings date are dropped when `since_year` is set. `zip_links` counts the cases linked by
    name + ZIP, the stricter of the two match rules.
    """
    where, args = _watchlist_filter(program, since_year, visa_violations_only, min_applications, state,
                                    sector)
    return rows(con, f"""
        SELECT e.employer_id, e.employer_name, e.dba, e.city, e.state, e.program, e.naics,
               e.n_applications, e.n_certified, e.willful_violator, e.h1b_dependent,
               COUNT(*) AS n_cases,
               SUM(m.method = 'clean name + ZIP') AS zip_links,
               COALESCE(SUM(v.case_violtn_cnt), 0) AS violations,
               COALESCE(SUM(v.h1b_violtn_cnt), 0) AS h1b_violations,
               COALESCE(SUM(v.h2b_violtn_cnt), 0) AS h2b_violations,
               COALESCE(SUM(v.bw_atp_amt), 0) AS back_wages,
               COALESCE(SUM(v.ee_violtd_cnt), 0) AS workers,
               COALESCE(SUM(v.cmp_assd), 0) AS penalties,
               MAX(NULLIF(v.findings_end_date, '')) AS latest_case
        FROM matches m JOIN employers e USING (employer_id) JOIN violation_cases v USING (case_id)
        WHERE {where}
        GROUP BY e.employer_id
        ORDER BY back_wages DESC, n_cases DESC, e.employer_id""", *args)


def watchlist_totals(con, **filters):
    """Totals for the watchlist, counting each WHD case once.

    A case can link to several employer rows (one company at two addresses, or in both programs),
    so adding up the watchlist rows would count it more than once.
    """
    where, args = _watchlist_filter(filters.get("program"), filters.get("since_year"),
                                    filters.get("visa_violations_only", False),
                                    filters.get("min_applications", 1), filters.get("state"),
                                    filters.get("sector"))
    return rows(con, f"""
        SELECT COUNT(*) AS cases, COALESCE(SUM(bw_atp_amt), 0) AS back_wages,
               COALESCE(SUM(cmp_assd), 0) AS penalties
        FROM violation_cases WHERE case_id IN (
            SELECT m.case_id
            FROM matches m JOIN employers e USING (employer_id) JOIN violation_cases v USING (case_id)
            WHERE {where})""", *args)[0]


# NAICS sectors (first two digits of the code). Three sectors span several two-digit prefixes.
SECTORS = {
    "11": "Agriculture, forestry, fishing and hunting", "21": "Mining, oil and gas",
    "22": "Utilities", "23": "Construction", "31-33": "Manufacturing", "42": "Wholesale trade",
    "44-45": "Retail trade", "48-49": "Transportation and warehousing", "51": "Information",
    "52": "Finance and insurance", "53": "Real estate and rental", "54": "Professional, scientific and technical services",
    "55": "Management of companies", "56": "Administrative, support and staffing services",
    "61": "Educational services", "62": "Health care and social assistance",
    "71": "Arts, entertainment and recreation", "72": "Accommodation and food services",
    "81": "Other services (repair, personal care, etc.)", "92": "Public administration",
}
SECTOR_PREFIXES = {k: [str(p) for p in range(int(k[:2]), int(k[-2:]) + 1)] for k in SECTORS}
_SECTOR_OF = {p: k for k, ps in SECTOR_PREFIXES.items() for p in ps}


def sector_of(naics):
    """The sector key ("54", "31-33", ...) for a NAICS code, or None when the code is missing or invalid."""
    return _SECTOR_OF.get((naics or "")[:2])


def _group_stats(con, key_sql, program=None, visa_violations_only=False):
    """Per-group visa employer counts and linked WHD case totals, each case counted once per group."""
    emp_where, args = ["1"], []
    if program:
        emp_where.append("e.program = ?")
        args.append(program)
    case_where = ["1"]
    if visa_violations_only:
        case_where.append("CASE e.program WHEN 'H-1B' THEN v.h1b_violtn_cnt WHEN 'H-2B' THEN v.h2b_violtn_cnt END > 0")
    emp = rows(con, f"""
        SELECT {key_sql} AS grp, COUNT(*) AS employers, SUM(n_applications) AS applications
        FROM employers e WHERE {" AND ".join(emp_where)} GROUP BY grp""", *args)
    linked = rows(con, f"""
        SELECT grp, COUNT(DISTINCT employer_id) AS employers_with_cases
        FROM (SELECT {key_sql} AS grp, e.employer_id
              FROM matches m JOIN employers e USING (employer_id) JOIN violation_cases v USING (case_id)
              WHERE {" AND ".join(emp_where + case_where)})
        GROUP BY grp""", *args)
    cases = rows(con, f"""
        SELECT grp, COUNT(*) AS cases, COALESCE(SUM(bw_atp_amt), 0) AS back_wages,
               COALESCE(SUM(cmp_assd), 0) AS penalties,
               COALESCE(SUM(h1b_violtn_cnt), 0) + COALESCE(SUM(h2b_violtn_cnt), 0) AS visa_violations
        FROM (SELECT DISTINCT {key_sql} AS grp, v.case_id, v.bw_atp_amt, v.cmp_assd, v.h1b_violtn_cnt,
                     v.h2b_violtn_cnt
              FROM matches m JOIN employers e USING (employer_id) JOIN violation_cases v USING (case_id)
              WHERE {" AND ".join(emp_where + case_where)})
        GROUP BY grp""", *args)
    out = {r["grp"]: dict(r, employers_with_cases=0, cases=0, back_wages=0.0, penalties=0.0,
                          visa_violations=0) for r in emp}
    for r in linked + cases:
        if r["grp"] in out:
            out[r["grp"]].update({k: v for k, v in r.items() if k != "grp"})
    for r in out.values():
        r["share_with_cases"] = r["employers_with_cases"] / r["employers"] if r["employers"] else 0
        r["cases_per_100"] = 100 * r["cases"] / r["employers"] if r["employers"] else 0
    return out


def state_stats(con, program=None, visa_violations_only=False):
    """One row per employer state: visa employers, how many have linked WHD cases, and case totals."""
    out = _group_stats(con, "e.state", program, visa_violations_only)
    return sorted(({**{k: v for k, v in r.items() if k != "grp"}, "state": r["grp"]}
                   for r in out.values() if r["grp"]), key=lambda r: r["state"])


def sector_stats(con, program=None, visa_violations_only=False):
    """One row per NAICS sector, like state_stats, most visa employers first.

    Codes outside the sector list (missing or malformed) are left out.
    """
    case = " ".join(f"WHEN substr(e.naics, 1, 2) = '{p}' THEN '{k}'" for p, k in _SECTOR_OF.items())
    out = _group_stats(con, f"CASE {case} END", program, visa_violations_only)
    return sorted(({**{k: v for k, v in r.items() if k != "grp"}, "sector": r["grp"], "name": SECTORS[r["grp"]]}
                   for r in out.values() if r["grp"]), key=lambda r: -r["employers"])


def case_years(con, employer_id):
    """Linked WHD cases and back wages per year the findings ended, for the employer page's chart."""
    return rows(con, """
        SELECT CAST(substr(v.findings_end_date, 1, 4) AS INTEGER) AS year, COUNT(*) AS cases,
               COALESCE(SUM(v.bw_atp_amt), 0) AS back_wages
        FROM matches m JOIN violation_cases v USING (case_id)
        WHERE m.employer_id = ? AND v.findings_end_date != ''
        GROUP BY year ORDER BY year""", employer_id)


def states(con):
    return [r["state"] for r in rows(con, "SELECT DISTINCT state FROM employers "
                                          "WHERE state != '' ORDER BY state")]


def match_label(method, rate):
    """Plain-language confidence for a name-based link."""
    pct = f"{rate:.0%}" if rate is not None else "an unknown share"
    return f"Matched by {method}; about {pct} of links made this way were wrong in the tax-ID test"


def sources(con):
    return rows(con, "SELECT source_id, file, rows, sha256, urls, created_utc, script FROM sources"
                     " ORDER BY source_id")

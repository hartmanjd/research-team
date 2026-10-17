"""Download the DOL Wage and Hour (WHD) enforcement table through the DOL API.

Needs a free API key from https://dataportal.dol.gov, set as env var DOL_API_KEY;
the script adds it to each request URL (?X-API-KEY=...), the same as a browser test.
Without it, the request goes out keyless (works only if a proxy adds the key). Writes one CSV with every column of the table
(violation counts, back wages and penalties under each law WHD enforces, child labor
minors, FLSA repeat/willful status; no personal contact fields exist in this table), plus
OUT.csv.manifest.json recording the source URL, columns, download time, row
count and checksum. The key is never written anywhere.

Usage: python3 fetch_whd.py OUT.csv   (re-run with the same OUT to resume)
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provenance import write_manifest

URL = "https://apiprod.dol.gov/v4/get/WHD/enforcement/json"
# Every column of the table, in DOL's order (load_dt: when DOL loaded the row).
FIELDS = ["case_id", "trade_nm", "legal_name", "street_addr_1_txt", "cty_nm", "st_cd", "zip_cd",
          "naic_cd", "naics_code_description", "case_violtn_cnt", "cmp_assd", "ee_violtd_cnt",
          "bw_atp_amt", "ee_atp_cnt", "findings_start_date", "findings_end_date", "flsa_violtn_cnt",
          "flsa_repeat_violator", "flsa_bw_atp_amt", "flsa_ee_atp_cnt", "flsa_mw_bw_atp_amt",
          "flsa_ot_bw_atp_amt", "flsa_15a3_bw_atp_amt", "flsa_cmp_assd_amt", "sca_violtn_cnt",
          "sca_bw_atp_amt", "sca_ee_atp_cnt", "mspa_violtn_cnt", "mspa_bw_atp_amt",
          "mspa_ee_atp_cnt", "mspa_cmp_assd_amt", "h1b_violtn_cnt", "h1b_bw_atp_amt",
          "h1b_ee_atp_cnt", "h1b_cmp_assd_amt", "fmla_violtn_cnt", "fmla_bw_atp_amt",
          "fmla_ee_atp_cnt", "fmla_cmp_assd_amt", "flsa_cl_violtn_cnt", "flsa_cl_minor_cnt",
          "flsa_cl_cmp_assd_amt", "dbra_violtn_cnt", "dbra_bw_atp_amt", "dbra_ee_atp_cnt",
          "h2a_violtn_cnt", "h2a_bw_atp_amt", "h2a_ee_atp_cnt", "h2a_cmp_assd_amt",
          "flsa_smw14_violtn_cnt", "flsa_smw14_bw_amt", "flsa_smw14_ee_atp_cnt",
          "cwhssa_violtn_cnt", "cwhssa_bw_amt", "cwhssa_ee_cnt", "osha_violtn_cnt",
          "osha_bw_atp_amt", "osha_ee_atp_cnt", "osha_cmp_assd_amt", "eppa_violtn_cnt",
          "eppa_bw_atp_amt", "eppa_ee_cnt", "eppa_cmp_assd_amt", "h1a_violtn_cnt", "h1a_bw_atp_amt",
          "h1a_ee_atp_cnt", "h1a_cmp_assd_amt", "crew_violtn_cnt", "crew_bw_atp_amt",
          "crew_ee_atp_cnt", "crew_cmp_assd_amt", "ccpa_violtn_cnt", "ccpa_bw_atp_amt",
          "ccpa_ee_atp_cnt", "flsa_smwpw_violtn_cnt", "flsa_smwpw_bw_atp_amt",
          "flsa_smwpw_ee_atp_cnt", "flsa_hmwkr_violtn_cnt", "flsa_hmwkr_bw_atp_amt",
          "flsa_hmwkr_ee_atp_cnt", "flsa_hmwkr_cmp_assd_amt", "ca_violtn_cnt", "ca_bw_atp_amt",
          "ca_ee_atp_cnt", "pca_violtn_cnt", "pca_bw_atp_amt", "pca_ee_atp_cnt",
          "flsa_smwap_violtn_cnt", "flsa_smwap_bw_atp_amt", "flsa_smwap_ee_atp_cnt",
          "flsa_smwft_violtn_cnt", "flsa_smwft_bw_atp_amt", "flsa_smwft_ee_atp_cnt",
          "flsa_smwl_violtn_cnt", "flsa_smwl_bw_atp_amt", "flsa_smwl_ee_atp_cnt",
          "flsa_smwmg_violtn_cnt", "flsa_smwmg_bw_atp_amt", "flsa_smwmg_ee_atp_cnt",
          "flsa_smwsl_violtn_cnt", "flsa_smwsl_bw_atp_amt", "flsa_smwsl_ee_atp_cnt",
          "eev_violtn_cnt", "h2b_violtn_cnt", "h2b_bw_atp_amt", "h2b_ee_atp_cnt", "sraw_violtn_cnt",
          "sraw_bw_atp_amt", "sraw_ee_atp_cnt", "load_dt"]
PAGE = 1000  # API returns 413 (too large) at 2000 rows with every column
PAUSE = 2  # seconds between pages; the API rate-limits bursts


def get(params):
    key = os.environ.get("DOL_API_KEY", "").strip()
    if key:
        params = {**params, "X-API-KEY": key}
    q = urllib.parse.urlencode(params)
    for attempt in range(9):
        try:
            req = urllib.request.Request(f"{URL}?{q}")
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                return json.loads(body).get("data", []) if body.strip() else []  # 204 = past the end
        except Exception as e:  # retry transient errors and rate limits (429)
            wait = getattr(e, "headers", None) and e.headers.get("Retry-After")
            wait = int(wait) if wait and wait.isdigit() else min(2 ** (attempt + 2), 300)
            print("retry", attempt, e, f"waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("API kept failing")


def main(out):
    # Resume: if OUT already has rows (an earlier run was cut off), continue after them.
    n = 0
    if os.path.exists(out) and os.path.getsize(out) > 0:
        with open(out, newline="") as f:
            r = csv.DictReader(f)
            n = sum(1 for _ in r)
            if r.fieldnames != FIELDS:
                raise SystemExit(f"{out} has different columns; delete it or pick a new file")
        print(f"resuming after {n} rows", file=sys.stderr)
    with open(out, "a" if n else "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if not n:
            w.writeheader()
        while True:
            rows = get({"limit": PAGE, "offset": n})  # no fields list: every column (a 110-name list is refused)
            if not rows:
                break
            w.writerows(rows)
            n += len(rows)
            f.flush()  # whole pages only, so a cut-off run resumes cleanly
            print(n, file=sys.stderr)
            time.sleep(PAUSE)
    write_manifest(out, __file__, sources=[{"url": URL, "note": "DOL Wage and Hour enforcement API"}],
                   params={"fields": FIELDS, "page_size": PAGE})
    print(f"wrote {n} rows to {out} (+ manifest)")


if __name__ == "__main__":
    main(sys.argv[1])

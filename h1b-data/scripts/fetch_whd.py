"""Download the DOL Wage and Hour (WHD) enforcement table through the DOL API.

Needs a free API key from https://dataportal.dol.gov, set as env var DOL_API_KEY;
the script adds it to each request URL (?X-API-KEY=...), the same as a browser test.
Without it, the request goes out keyless (works only if a proxy adds the key). Writes one CSV with the employer and violation
columns used for matching (no personal contact fields exist in this table), plus
OUT.csv.manifest.json recording the source URL, columns, download time, row
count and checksum. The key is never written anywhere.

Usage: python3 fetch_whd.py OUT.csv   (re-run with the same OUT to resume)
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provenance import write_manifest

URL = "https://apiprod.dol.gov/v4/get/WHD/enforcement/json"
FIELDS = ["case_id", "trade_nm", "legal_name", "street_addr_1_txt", "cty_nm", "st_cd",
          "zip_cd", "naic_cd", "findings_start_date", "findings_end_date",
          "case_violtn_cnt", "bw_atp_amt", "ee_violtd_cnt", "cmp_assd",
          "h1b_violtn_cnt", "h1b_bw_atp_amt", "h1b_ee_atp_cnt", "h1b_cmp_assd_amt",
          "h2b_violtn_cnt", "h2b_bw_atp_amt", "h2b_ee_atp_cnt",
          "h2a_violtn_cnt", "flsa_violtn_cnt", "load_dt"]  # load_dt: when DOL loaded the row
PAGE = 2000  # API returns 413 above ~5000 rows with these fields
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
            rows = get({"limit": PAGE, "offset": n, "fields": ",".join(FIELDS)})
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

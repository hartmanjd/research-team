"""Match WHD violation cases to OFLC filers by name and address.

WHD has no FEIN, so each case is tried against filers under several rules,
using both the WHD trade name and legal name. Reports the share of
H-1B-violation cases (vs LCA filers) and H-2B-violation cases (vs H-2B filers)
that find at least one filer.

Usage: python3 match_whd.py whd.csv filers_lca.csv filers_h2b.csv OUT_DIR
"""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from employer_keys import raw_name, clean_name, zip5

RULES = {"exact name": ["name_raw"], "clean name": ["name_clean"],
         "clean name + state": ["name_clean", "state"], "clean name + ZIP": ["name_clean", "zip5"]}


def whd_keys(whd):
    parts = []
    for col in ["trade_nm", "legal_name"]:
        p = whd[["case_id", "st_cd", "zip_cd", "findings_end_date"]].copy()
        p["name_raw"] = whd[col].map(raw_name)
        p["name_clean"] = whd[col].map(clean_name)
        parts.append(p)
    k = pd.concat(parts)
    k["state"] = k.st_cd.str.upper().str.strip()
    k["zip5"] = k.zip_cd.map(zip5)
    return k[k.name_clean != ""].drop_duplicates()


def filer_keys(f):
    a = f[["name_raw", "name_clean", "state", "zip5", "fein"]]
    b = f[["dba_clean", "state", "zip5", "fein"]].rename(columns={"dba_clean": "name_clean"})
    b = b[b.name_clean != ""].assign(name_raw="")
    return pd.concat([a, b]).drop_duplicates()


def rates(cases, filers, label):
    keys = whd_keys(cases)
    fk = filer_keys(filers)
    out = []
    recent = set(cases.loc[cases.findings_end_date.fillna("") >= "2020", "case_id"])
    for rule, cols in RULES.items():
        m = keys.merge(fk, on=cols)
        m = m[m[cols[0]] != ""]
        hit = set(m.case_id)
        out.append({"cases": label, "rule": rule, "n_cases": len(cases),
                    "matched": len(hit), "match_rate": len(hit) / max(len(cases), 1),
                    "n_cases_2020plus": len(recent),
                    "match_rate_2020plus": len(hit & recent) / max(len(recent), 1),
                    "avg_filers_per_matched_case": m.groupby("case_id").fein.nunique().mean()})
    return out


def main(whd_p, lca_p, h2b_p, out_dir):
    whd = pd.read_csv(whd_p, dtype=str, keep_default_na=False)
    lca = pd.read_csv(lca_p, dtype=str, keep_default_na=False)
    h2b = pd.read_csv(h2b_p, dtype=str, keep_default_na=False)
    num = lambda c: pd.to_numeric(whd[c], errors="coerce").fillna(0)
    res = rates(whd[num("h1b_violtn_cnt") > 0], lca, "H-1B violation cases vs H-1B filers")
    res += rates(whd[num("h2b_violtn_cnt") > 0], h2b, "H-2B violation cases vs H-2B filers")
    df = pd.DataFrame(res)
    df.to_csv(os.path.join(out_dir, "whd_match_rates.csv"), index=False)
    print(f"WHD rows={len(whd)}  H-1B violation cases={(num('h1b_violtn_cnt') > 0).sum()}"
          f"  H-2B violation cases={(num('h2b_violtn_cnt') > 0).sum()}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main(*sys.argv[1:])

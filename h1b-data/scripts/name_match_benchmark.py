"""Use FEIN (federal tax ID) as an answer key to test name/address matching rules.

WHD enforcement records carry no FEIN, so they must be joined to filers by name
and address. Both OFLC files DO carry FEIN, so employers that file in both the
H-1B (LCA) and H-2B programs give a labeled set: we can see how often each
name rule finds the right employer (recall) and how often a name-rule match
points to a different FEIN (false-match rate).

Writes OUT.csv and OUT.csv.manifest.json (input checksums).

Usage: python3 name_match_benchmark.py filers_lca.csv filers_h2b.csv OUT.csv
"""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provenance import write_manifest


def explode_fein(df):
    df = df.copy()
    df["fein"] = df.fein.fillna("").str.split(";")
    return df.explode("fein")


def main(lca_p, h2b_p, out):
    lca = pd.read_csv(lca_p, dtype=str, keep_default_na=False)
    h2b = pd.read_csv(h2b_p, dtype=str, keep_default_na=False)
    L, H = explode_fein(lca), explode_fein(h2b)
    shared = set(L.fein) & set(H.fein) - {""}
    rows = []
    rules = {
        "exact name": ["name_raw"],
        "clean name": ["name_clean"],
        "clean name + state": ["name_clean", "state"],
        "clean name + ZIP": ["name_clean", "zip5"],
    }
    for rule, keys in rules.items():
        m = L.merge(H, on=keys, suffixes=("_l", "_h"))
        m = m[m[keys[0]] != ""]
        found = set(m.loc[m.fein_l == m.fein_h, "fein_l"])
        pairs = m[["fein_l", "fein_h"]].drop_duplicates()
        wrong = (pairs.fein_l != pairs.fein_h).sum()
        rows.append({"rule": rule, "true_shared_employers": len(shared),
                     "found": len(found & shared), "recall": len(found & shared) / len(shared),
                     "matched_pairs": len(pairs), "pairs_with_different_fein": int(wrong),
                     "false_match_rate": wrong / max(len(pairs), 1)})
    res = pd.DataFrame(rows)
    res.to_csv(out, index=False)
    write_manifest(out, __file__, inputs=[lca_p, h2b_p], params={"rules": rules})
    print(res.to_string(index=False))

    # How badly do names fragment one employer? (same FEIN, several names)
    for name, df in [("LCA", L), ("H-2B", H)]:
        g = df[df.fein != ""].groupby("fein")
        print(f"{name}: FEINs={g.ngroups} with >1 raw name={(g.name_raw.nunique() > 1).mean():.1%}"
              f" with >1 clean name={(g.name_clean.nunique() > 1).mean():.1%}"
              f" with >1 ZIP={(g.zip5.nunique() > 1).mean():.1%}")


if __name__ == "__main__":
    main(*sys.argv[1:])

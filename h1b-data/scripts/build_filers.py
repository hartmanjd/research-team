"""Collapse OFLC disclosure CSVs (one row per application) into one row per employer.

Keeps only employer-level fields (name, DBA, address, FEIN, NAICS) and drops
all contact, attorney and preparer names, phones and emails.

Usage: python3 build_filers.py OUT.csv IN1.csv [IN2.csv ...]
"""
import sys
import pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__file__))
from employer_keys import raw_name, clean_name, zip5, fein

KEEP = ["CASE_NUMBER", "CASE_STATUS", "VISA_CLASS", "EMPLOYER_NAME", "TRADE_NAME_DBA",
        "EMPLOYER_ADDRESS1", "EMPLOYER_CITY", "EMPLOYER_STATE", "EMPLOYER_POSTAL_CODE",
        "EMPLOYER_FEIN", "NAICS_CODE", "H-1B_DEPENDENT", "WILLFUL_VIOLATOR"]


def main(out, *ins):
    frames = []
    for p in ins:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, usecols=lambda c: c in KEEP)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df[df.CASE_NUMBER.str.strip() != ""]  # sheets carry many blank padding rows
    if "VISA_CLASS" not in df:
        df["VISA_CLASS"] = "H-2B"
    df["name_raw"] = df.EMPLOYER_NAME.map(raw_name)
    df["name_clean"] = df.EMPLOYER_NAME.map(clean_name)
    df["dba_clean"] = df.get("TRADE_NAME_DBA", "").map(clean_name) if "TRADE_NAME_DBA" in df else ""
    df["zip5"] = df.EMPLOYER_POSTAL_CODE.map(zip5)
    df["state"] = df.EMPLOYER_STATE.str.upper().str.strip()
    df["fein"] = df.EMPLOYER_FEIN.map(fein) if "EMPLOYER_FEIN" in df else ""
    df["certified"] = df.CASE_STATUS.str.upper().str.startswith("CERTIFIED")
    for c in ["H-1B_DEPENDENT", "WILLFUL_VIOLATOR"]:
        if c not in df:
            df[c] = ""
    g = df.groupby(["name_clean", "state", "zip5"], dropna=False)
    emp = g.agg(employer_name=("EMPLOYER_NAME", "first"), dba=("TRADE_NAME_DBA", "first"),
                name_raw=("name_raw", "first"), dba_clean=("dba_clean", "first"),
                city=("EMPLOYER_CITY", "first"), address=("EMPLOYER_ADDRESS1", "first"),
                fein=("fein", lambda s: ";".join(sorted({x for x in s if x}))),
                naics=("NAICS_CODE", "first"), visa_classes=("VISA_CLASS", lambda s: ";".join(sorted(set(s)))),
                n_applications=("CASE_NUMBER", "size"), n_certified=("certified", "sum"),
                h1b_dependent=("H-1B_DEPENDENT", lambda s: (s.str.upper() == "YES").any()),
                willful_violator=("WILLFUL_VIOLATOR", lambda s: (s.str.upper() == "YES").any()),
                ).reset_index()
    emp.to_csv(out, index=False)
    print(f"{len(df)} applications -> {len(emp)} employer rows -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

"""Collapse OFLC disclosure CSVs (one row per application) into one row per employer.

Keeps only employer-level fields (name, DBA, address, FEIN, NAICS) and drops
all contact, attorney and preparer names, phones and emails.

Writes two tables, each with a .manifest.json (checksums, inputs, sources):
  OUT.csv               one row per employer (cleaned name + state + ZIP)
  OUT_applications.csv  one row per application: its DOL case number, status,
                        visa class, source file and the employer key, so every
                        employer row can be traced back to its exact filings.

Pass the inputs in date order (Q1 before Q2 ...). A case number that appears
in more than one file (e.g. certified in Q1, withdrawn in Q3) is kept once,
with its latest record, so it is not counted twice.

Usage: python3 build_filers.py OUT.csv IN1.csv [IN2.csv ...] [--source-url URL ...]
"""
import argparse, os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from employer_keys import raw_name, clean_name, zip5, fein
from provenance import write_manifest

KEEP = ["CASE_NUMBER", "CASE_STATUS", "VISA_CLASS", "EMPLOYER_NAME", "TRADE_NAME_DBA",
        "EMPLOYER_ADDRESS1", "EMPLOYER_CITY", "EMPLOYER_STATE", "EMPLOYER_POSTAL_CODE",
        "EMPLOYER_FEIN", "NAICS_CODE", "H-1B_DEPENDENT", "WILLFUL_VIOLATOR"]
KEY = ["name_clean", "state", "zip5"]
DEFAULT_SOURCE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"


def applications_path(out):
    root, ext = os.path.splitext(out)
    return f"{root}_applications{ext or '.csv'}"


def load(ins):
    frames = []
    for p in ins:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, usecols=lambda c: c in KEEP)
        df["source_file"] = os.path.basename(p)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df[df.CASE_NUMBER.str.strip() != ""]  # sheets carry many blank padding rows
    df = df.drop_duplicates("CASE_NUMBER", keep="last").copy()  # latest decision wins
    if "VISA_CLASS" not in df:
        df["VISA_CLASS"] = "H-2B"
    for c in ["TRADE_NAME_DBA", "H-1B_DEPENDENT", "WILLFUL_VIOLATOR", "EMPLOYER_FEIN"]:
        if c not in df:
            df[c] = ""
    df["name_raw"] = df.EMPLOYER_NAME.map(raw_name)
    df["name_clean"] = df.EMPLOYER_NAME.map(clean_name)
    df["dba_clean"] = df.TRADE_NAME_DBA.map(clean_name)
    df["zip5"] = df.EMPLOYER_POSTAL_CODE.map(zip5)
    df["state"] = df.EMPLOYER_STATE.str.upper().str.strip()
    df["fein"] = df.EMPLOYER_FEIN.map(fein)
    df["certified"] = df.CASE_STATUS.str.upper().str.startswith("CERTIFIED")
    return df


def employers(df):
    g = df.groupby(KEY, dropna=False)
    return g.agg(employer_name=("EMPLOYER_NAME", "first"), dba=("TRADE_NAME_DBA", "first"),
                 name_raw=("name_raw", "first"), dba_clean=("dba_clean", "first"),
                 city=("EMPLOYER_CITY", "first"), address=("EMPLOYER_ADDRESS1", "first"),
                 fein=("fein", lambda s: ";".join(sorted({x for x in s if x}))),
                 naics=("NAICS_CODE", "first"), visa_classes=("VISA_CLASS", lambda s: ";".join(sorted(set(s)))),
                 n_applications=("CASE_NUMBER", "size"), n_certified=("certified", "sum"),
                 h1b_dependent=("H-1B_DEPENDENT", lambda s: (s.str.upper() == "YES").any()),
                 willful_violator=("WILLFUL_VIOLATOR", lambda s: (s.str.upper() == "YES").any()),
                 source_files=("source_file", lambda s: ";".join(sorted(set(s)))),
                 ).reset_index()


def applications(df):
    a = df[["CASE_NUMBER", "CASE_STATUS", "VISA_CLASS", "fein", "source_file"] + KEY]
    return a.rename(columns={"CASE_NUMBER": "case_number", "CASE_STATUS": "case_status",
                             "VISA_CLASS": "visa_class"})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--source-url", action="append", default=[],
                    help="where the raw disclosure files came from (repeatable)")
    a = ap.parse_args(argv)
    df = load(a.inputs)
    emp = employers(df)
    apps = applications(df)
    app_out = applications_path(a.out)
    emp.to_csv(a.out, index=False)
    apps.to_csv(app_out, index=False)
    sources = [{"url": u} for u in (a.source_url or [DEFAULT_SOURCE])]
    for path in (a.out, app_out):
        write_manifest(path, __file__, inputs=a.inputs, sources=sources)
    print(f"{len(df)} applications -> {len(emp)} employer rows -> {a.out}; "
          f"case numbers -> {app_out}")


if __name__ == "__main__":
    main()

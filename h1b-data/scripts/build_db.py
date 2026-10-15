"""Build one SQLite database from the employer tables and the WHD enforcement data.

Tables:
  sources          one row per input file, from its manifest (checksum, rows, URLs)
  employers        one row per employer per program (H-1B or H-2B)
  applications     one row per visa application, with its DOL case number
  violation_cases  one row per WHD enforcement case
  matches          links a WHD case to an employer: how it was matched and the
                   rule's false-match rate on the tax-ID benchmark

Every input must have a manifest that still matches it (see provenance.py), and
every row in the data tables carries the source_id of the file it came from.
WHD cases have no tax ID, so they are linked by cleaned name + ZIP or cleaned
name + state (trade name or legal name against employer name or DBA); a pair
keeps the stronger rule. Writes OUT.db.manifest.json.

Usage: python3 build_db.py OUT.db --lca filers_lca.csv --h2b filers_h2b.csv
                           --whd whd.csv --benchmark name_match_benchmark.csv
"""
import argparse, json, os, sqlite3, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_filers import applications_path
from employer_keys import clean_name, zip5
from provenance import verify_manifest, write_manifest

# Strongest first: a (case, employer) pair keeps the first rule that links it.
MATCH_RULES = {"clean name + ZIP": ["name_clean", "zip5"],
               "clean name + state": ["name_clean", "state"]}

SCHEMA = """
CREATE TABLE sources (
  source_id INTEGER PRIMARY KEY, file TEXT, sha256 TEXT, bytes INTEGER, rows INTEGER,
  created_utc TEXT, script TEXT, urls TEXT, manifest TEXT);
CREATE TABLE employers (
  employer_id INTEGER PRIMARY KEY, program TEXT, name_clean TEXT, state TEXT, zip5 TEXT,
  employer_name TEXT, dba TEXT, name_raw TEXT, dba_clean TEXT, city TEXT, address TEXT,
  fein TEXT, naics TEXT, visa_classes TEXT, n_applications INTEGER, n_certified INTEGER,
  h1b_dependent INTEGER, willful_violator INTEGER, source_files TEXT,
  source_id INTEGER REFERENCES sources);
CREATE TABLE applications (
  case_number TEXT, program TEXT, employer_id INTEGER REFERENCES employers,
  case_status TEXT, visa_class TEXT, fein TEXT, source_file TEXT,
  source_id INTEGER REFERENCES sources);
CREATE TABLE violation_cases (
  case_id INTEGER PRIMARY KEY, trade_nm TEXT, legal_name TEXT, street_addr_1_txt TEXT,
  cty_nm TEXT, st_cd TEXT, zip_cd TEXT, naic_cd TEXT, findings_start_date TEXT,
  findings_end_date TEXT, case_violtn_cnt INTEGER, bw_atp_amt REAL, ee_violtd_cnt INTEGER,
  cmp_assd REAL, h1b_violtn_cnt INTEGER, h1b_bw_atp_amt REAL, h1b_ee_atp_cnt INTEGER,
  h1b_cmp_assd_amt REAL, h2b_violtn_cnt INTEGER, h2b_bw_atp_amt REAL, h2b_ee_atp_cnt INTEGER,
  h2a_violtn_cnt INTEGER, flsa_violtn_cnt INTEGER, load_dt TEXT,
  source_id INTEGER REFERENCES sources);
CREATE TABLE matches (
  case_id INTEGER REFERENCES violation_cases, employer_id INTEGER REFERENCES employers,
  method TEXT, est_false_match_rate REAL, whd_name_field TEXT, employer_name_field TEXT,
  PRIMARY KEY (case_id, employer_id));
CREATE INDEX employers_fein ON employers(fein);
CREATE INDEX employers_name ON employers(name_clean, state);
CREATE INDEX applications_employer ON applications(employer_id);
CREATE INDEX applications_case ON applications(case_number);
CREATE INDEX matches_employer ON matches(employer_id);
"""
INT_COLS = ["n_applications", "n_certified", "case_violtn_cnt", "ee_violtd_cnt", "h1b_violtn_cnt",
            "h1b_ee_atp_cnt", "h2b_violtn_cnt", "h2b_ee_atp_cnt", "h2a_violtn_cnt", "flsa_violtn_cnt"]
REAL_COLS = ["bw_atp_amt", "cmp_assd", "h1b_bw_atp_amt", "h1b_cmp_assd_amt", "h2b_bw_atp_amt"]


def read(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def add_source(con, path):
    m = verify_manifest(path)  # refuses a file that changed since its manifest
    cur = con.execute(
        "INSERT INTO sources (file, sha256, bytes, rows, created_utc, script, urls, manifest)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (m["file"], m["sha256"], m["bytes"], m["rows"], m["created_utc"], m["script"],
         ";".join(s["url"] for s in m.get("sources", []) if s.get("url")), json.dumps(m)))
    return cur.lastrowid


def numeric(df):
    for c in INT_COLS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in REAL_COLS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_program(con, program, filers_path, next_id):
    emp = read(filers_path)
    emp.insert(0, "employer_id", range(next_id, next_id + len(emp)))
    emp.insert(1, "program", program)
    for c in ["h1b_dependent", "willful_violator"]:
        emp[c] = (emp[c] == "True").astype(int)
    emp["source_id"] = add_source(con, filers_path)
    numeric(emp).to_sql("employers", con, if_exists="append", index=False)

    app_path = applications_path(filers_path)
    apps = read(app_path).merge(emp[["employer_id", "name_clean", "state", "zip5"]],
                                on=["name_clean", "state", "zip5"], how="left")
    if apps.employer_id.isna().any():
        raise ValueError(f"{os.path.basename(app_path)} has applications with no employer row")
    apps["program"] = program
    apps["source_id"] = add_source(con, app_path)
    apps[["case_number", "program", "employer_id", "case_status", "visa_class", "fein",
          "source_file", "source_id"]].to_sql("applications", con, if_exists="append", index=False)
    return emp


def whd_keys(whd):
    parts = []
    for col, label in [("trade_nm", "trade name"), ("legal_name", "legal name")]:
        p = pd.DataFrame({"case_id": whd.case_id, "whd_name_field": label,
                          "name_clean": whd[col].map(clean_name),
                          "state": whd.st_cd.str.upper().str.strip(), "zip5": whd.zip_cd.map(zip5)})
        parts.append(p)
    k = pd.concat(parts)
    return k[k.name_clean != ""]


def employer_keys(emp):
    a = emp[["employer_id", "name_clean", "state", "zip5"]].assign(employer_name_field="name")
    b = emp[["employer_id", "dba_clean", "state", "zip5"]].rename(columns={"dba_clean": "name_clean"})
    b = b[b.name_clean != ""].assign(employer_name_field="DBA")
    return pd.concat([a, b])


def match(whd, emp, false_rates):
    wk, ek = whd_keys(whd), employer_keys(emp)
    found = []
    for rule, cols in MATCH_RULES.items():
        m = wk.merge(ek, on=cols)
        m = m[(m.name_clean != "") & (m[cols[1]] != "")]
        found.append(m.assign(method=rule, est_false_match_rate=false_rates.get(rule)))
    m = pd.concat(found)  # strongest rule first, so keep="first" keeps it
    m = m.drop_duplicates(["case_id", "employer_id"], keep="first")
    return m[["case_id", "employer_id", "method", "est_false_match_rate",
              "whd_name_field", "employer_name_field"]]


def build(out, lca, h2b, whd_path, bench):
    if os.path.exists(out):
        os.remove(out)
    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    lca_emp = load_program(con, "H-1B", lca, 1)
    h2b_emp = load_program(con, "H-2B", h2b, len(lca_emp) + 1)
    emp = pd.concat([lca_emp, h2b_emp])

    whd = read(whd_path)
    whd["source_id"] = add_source(con, whd_path)
    whd = numeric(whd)
    whd["case_id"] = whd.case_id.astype(int)
    whd.to_sql("violation_cases", con, if_exists="append", index=False)

    add_source(con, bench)
    false_rates = dict(zip(read(bench).rule, pd.to_numeric(read(bench).false_match_rate)))
    m = match(whd, emp, false_rates)
    m.to_sql("matches", con, if_exists="append", index=False)
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["sources", "employers", "applications", "violation_cases", "matches"]}
    con.close()
    inputs = [lca, applications_path(lca), h2b, applications_path(h2b), whd_path, bench]
    write_manifest(out, __file__, inputs=inputs, params={"match_rules": MATCH_RULES, "tables": counts})
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--lca", required=True)
    ap.add_argument("--h2b", required=True)
    ap.add_argument("--whd", required=True)
    ap.add_argument("--benchmark", required=True)
    a = ap.parse_args(argv)
    counts = build(a.out, a.lca, a.h2b, a.whd, a.benchmark)
    print(f"{a.out}: " + ", ".join(f"{t}={n}" for t, n in counts.items()))


if __name__ == "__main__":
    main()

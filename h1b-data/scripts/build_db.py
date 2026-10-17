"""Build one SQLite database from the employer tables and the WHD enforcement data.

Tables:
  sources          one row per input file, from its manifest (checksum, rows, URLs)
  employers        one row per employer per program (H-1B or H-2B)
  applications     one row per visa application: its DOL case number and every
                   column of the public disclosure file (H-2B-only columns are
                   blank on H-1B rows and the other way round)
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
from fetch_whd import FIELDS as WHD_FIELDS
from employer_keys import clean_name, zip5
from provenance import verify_manifest, write_manifest

# Strongest first: a (case, employer) pair keeps the first rule that links it.
MATCH_RULES = {"clean name + ZIP": ["name_clean", "zip5"],
               "clean name + state": ["name_clean", "state"]}

# WHD columns: counts (..._cnt) are whole numbers, back wages and penalties (..._amt, cmp_assd) are
# dollars, and the rest (names, address, codes, dates, the FLSA repeat/willful flag) are text.
WHD_INT_COLS = [c for c in WHD_FIELDS if c.endswith("_cnt")]
WHD_REAL_COLS = [c for c in WHD_FIELDS if c.endswith("_amt") or c == "cmp_assd"]


def _whd_type(c):
    return ("INTEGER PRIMARY KEY" if c == "case_id" else "INTEGER" if c in WHD_INT_COLS else
            "REAL" if c in WHD_REAL_COLS else "TEXT")


SCHEMA = """
CREATE TABLE sources (
  source_id INTEGER PRIMARY KEY, file TEXT, sha256 TEXT, bytes INTEGER, rows INTEGER,
  created_utc TEXT, script TEXT, urls TEXT, manifest TEXT);
CREATE TABLE employers (
  employer_id INTEGER PRIMARY KEY, program TEXT, name_clean TEXT, state TEXT, zip5 TEXT,
  employer_name TEXT, dba TEXT, name_raw TEXT, dba_clean TEXT, city TEXT, address TEXT,
  address2 TEXT, postal_code TEXT, phone TEXT, phone_ext TEXT,
  fein TEXT, naics TEXT, visa_classes TEXT, n_applications INTEGER, n_certified INTEGER,
  h1b_dependent INTEGER, willful_violator INTEGER, source_files TEXT,
  source_id INTEGER REFERENCES sources);
{violation_cases}
CREATE TABLE matches (
  case_id INTEGER REFERENCES violation_cases, employer_id INTEGER REFERENCES employers,
  method TEXT, est_false_match_rate REAL, whd_name_field TEXT, employer_name_field TEXT,
  PRIMARY KEY (case_id, employer_id));
CREATE INDEX employers_fein ON employers(fein);
CREATE INDEX employers_name ON employers(name_clean, state);
CREATE INDEX matches_employer ON matches(employer_id);
""".format(violation_cases="CREATE TABLE violation_cases (\n  " + ",\n  ".join(
    f"{c} {_whd_type(c)}" for c in WHD_FIELDS) + ",\n  source_id INTEGER REFERENCES sources);")
INT_COLS = ["n_applications", "n_certified"] + WHD_INT_COLS
REAL_COLS = WHD_REAL_COLS
# Disclosure columns stored as numbers, so wages and worker counts can be compared and summed.
APP_INT_COLS = ["total_worker_positions", "new_employment", "continued_employment",
                "change_previous_employment", "new_concurrent_employment", "change_employer",
                "amended_petition", "worksite_workers", "total_worksite_locations",
                "cap_subject_workers", "cap_exempt_workers", "total_workers_requested",
                "total_workers_certified", "training_months", "work_experience_months",
                "supervise_how_many"]
APP_REAL_COLS = ["wage_rate_of_pay_from", "wage_rate_of_pay_to", "prevailing_wage",
                 "basic_wage_rate_from", "basic_wage_rate_to", "overtime_rate_from",
                 "overtime_rate_to", "anticipated_number_of_hours", "sunday_hours", "monday_hours",
                 "tuesday_hours", "wednesday_hours", "thursday_hours", "friday_hours",
                 "saturday_hours"]
# Disclosure columns the website reads; created empty if no input file has them.
APP_REQUIRED = ["decision_date", "job_title", "soc_code", "soc_title", "begin_date", "end_date",
                "requested_begin_date", "requested_end_date", "worksite_city", "worksite_state",
                "total_worker_positions", "total_workers_requested", "total_workers_certified",
                "wage_rate_of_pay_from", "wage_rate_of_pay_to", "wage_unit_of_pay", "basic_wage_rate_from",
                "basic_wage_rate_to", "per", "prevailing_wage", "pw_unit_of_pay", "pw_wage_level",
                "lawfirm_name_business_name", "agent_attorney_first_name", "agent_attorney_last_name",
                "attorney_agent_first_name", "attorney_agent_last_name"]
# Shown first in the applications table; the remaining disclosure columns follow in file order.
APP_FIRST = ["case_number", "program", "employer_id", "case_status", "visa_class", "fein",
             "source_file", "source_id"]


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


def numeric(df, int_cols=INT_COLS, real_cols=REAL_COLS):
    for c in int_cols:
        if c in df:
            df[c] = pd.to_numeric(df[c].astype("string").str.replace(",", ""), errors="coerce").round().astype("Int64")
    for c in real_cols:
        if c in df:
            df[c] = pd.to_numeric(df[c].astype("string").str.replace(r"[$,]", "", regex=True),
                                  errors="coerce")
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
    apps["employer_id"] = apps.employer_id.astype(int)
    rest = [c for c in apps.columns if c not in APP_FIRST and c not in ("name_clean", "state", "zip5")]
    return emp, apps[APP_FIRST + rest]


def load_applications(con, frames):
    """One applications table for both programs; columns one program lacks stay empty."""
    cols = list(dict.fromkeys([c for f in frames for c in f.columns] + APP_REQUIRED))
    # Text unless listed as a number, so ZIPs, phones and codes keep their leading zeros.
    types = {c: "INTEGER" if c in APP_INT_COLS + ["employer_id", "source_id"] else
             "REAL" if c in APP_REAL_COLS else "TEXT" for c in cols}
    for f in frames:  # one at a time, to keep memory down
        numeric(f.reindex(columns=cols), APP_INT_COLS, APP_REAL_COLS).to_sql(
            "applications", con, if_exists="append", index=False, dtype=types)
    con.execute("CREATE INDEX applications_employer ON applications(employer_id)")
    con.execute("CREATE UNIQUE INDEX applications_case ON applications(case_number)")


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
    lca_emp, lca_apps = load_program(con, "H-1B", lca, 1)
    h2b_emp, h2b_apps = load_program(con, "H-2B", h2b, len(lca_emp) + 1)
    load_applications(con, [lca_apps, h2b_apps])
    emp = pd.concat([lca_emp, h2b_emp])

    whd = read(whd_path).reindex(columns=WHD_FIELDS)  # an older, narrower download leaves columns empty
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

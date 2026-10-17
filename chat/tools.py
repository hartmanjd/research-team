"""The lookups the chat model may call, as tool definitions plus the code that runs them.

Each tool is a thin wrapper over a function in dashboard/queries.py, so the chat answers from the
same tested queries as the website. Results are trimmed to what an answer needs and always carry
the record IDs to cite: `employer_id`, WHD `case_id` and LCA/H-2B `case_number`.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dashboard"))
import queries as q  # noqa: E402

MAX_ROWS = 25
PROGRAMS = ["H-1B", "H-2B"]
WATCHLIST_SORTS = ["back_wages", "n_cases", "violations", "visa_violations", "workers", "penalties",
                   "n_applications"]
GROUP_SORTS = ["employers", "employers_with_cases", "share_with_cases", "cases", "cases_per_100",
               "back_wages", "penalties", "visa_violations"]


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


# What the fields mean, for any model that reads the tool results (the chat and the MCP server).
DATA_NOTES = """- Applications are FY2025 DOL disclosure records (LCA for H-1B, H-2B certifications), one row per case number, latest status.
- An employer row is one company name at one address in one program; one company can have several rows. Rows sharing a tax ID are listed under same_tax_id_elsewhere.
- WHD cases cover every law WHD enforces (minimum wage, overtime, child labor, H-1B, H-2B, H-2A and others) and every year in the data, not only visa violations. Say "visa-program violations" only for h1b_violations on an H-1B employer or h2b_violations on an H-2B employer.
- WHD records have no tax ID, so cases are linked to employers by cleaned name plus ZIP code or state. Some links are wrong (about 3 to 4 percent in a tax-ID test). When a single case drives your answer, mention that it is a name match.
- A case with 0 violations and $0 back wages means WHD investigated and recorded no violations.
- Each case's laws list says which laws WHD found violations under (minimum wage and overtime, child labor, family leave, federal contracts, the visa programs and others), with violations, back wages, workers owed and penalties for each. child_labor_minors, repeat_violator (WHD's own Repeat or Willful finding under the FLSA) and the minimum wage, overtime and retaliation back wage split appear when WHD recorded them. WHD publishes these counts, not a description of what happened.
- red_flags are patterns in the employer's own FY2025 applications (wages at the floor, mostly entry-level wage levels, many withdrawn or denied applications, most workers placed outside the home state). They are reasons for a closer look, not evidence of a violation; say so.
- dol_debarments are entries on DOL's published debarment lists (H-1B, H-2A, H-2B, permanent labor certification) whose name, and state when DOL gives one, match the employer. Debarment is a DOL enforcement finding. The match is by name, so say it is a name match.
- willful_violator is the employer's own Yes/No answer on its applications, not a DOL finding. It counts only when most applications say Yes; willful_yes gives the count.
- Money is in U.S. dollars. back_wages is the back wages WHD found owed; penalties are civil money penalties assessed."""

_PROGRAM = {"type": "string", "enum": PROGRAMS, "description": "Visa program: H-1B or H-2B"}
_VISA_ONLY = {"type": "boolean", "description": "Count only WHD cases that found violations of the "
              "employer's own visa program (H-1B or H-2B)"}
_LIMIT = {"type": "integer", "description": f"How many rows to return, at most {MAX_ROWS} (default 10)"}

TOOLS = [
    {"name": "search_employers",
     "description": "Find visa employers by company name, trade name (DBA) or 9-digit tax ID (FEIN). "
                    "Returns up to 10 matches with employer_id, program, location, applications and "
                    "linked WHD case count. One company can have several rows: one per program and address.",
     "input_schema": _schema({"query": {"type": "string", "description": "Name, DBA or tax ID"}}, ["query"])},
    {"name": "get_employer",
     "description": "One employer's details: address, tax ID, industry, application counts, flags, "
                    "totals of its linked WHD cases, each linked case (case_id, dates, violations, back "
                    "wages, penalties, which laws were violated, how it was matched), its most common jobs and how its offered wages "
                    "compare with the prevailing wage, other rows sharing its tax ID, and any matching entry on DOL's "
                    "published debarment lists.",
     "input_schema": _schema({"employer_id": {"type": "integer"}}, ["employer_id"])},
    {"name": "list_applications",
     "description": "An employer's visa applications, newest decision first: case_number, status, job, "
                    "worksite, workers, offered and prevailing wage, law firm.",
     "input_schema": _schema({"employer_id": {"type": "integer"}, "limit": _LIMIT}, ["employer_id"])},
    {"name": "get_application",
     "description": "One visa application by its DOL case number (like I-200-25126-941960 or "
                    "H-300-25001-123456): job, workers, dates, worksite, offered against prevailing wage, "
                    "law firm and the employer that filed it.",
     "input_schema": _schema({"case_number": {"type": "string"}}, ["case_number"])},
    {"name": "watchlist",
     "description": "Visa employers that have linked WHD cases, ranked, with filters, plus totals that "
                    "count each case once. Use it for rankings and counts across employers.",
     "input_schema": _schema({
         "program": _PROGRAM,
         "state": {"type": "string", "description": "Two-letter employer state, like TX"},
         "sector": {"type": "string", "enum": list(q.SECTORS), "description": "NAICS sector key"},
         "since_year": {"type": "integer", "description": "Keep cases whose findings ended in or after this year"},
         "visa_violations_only": _VISA_ONLY,
         "min_applications": {"type": "integer", "description": "Only employers with at least this many applications"},
         "sort_by": {"type": "string", "enum": WATCHLIST_SORTS, "description": "Highest first (default back_wages)"},
         "limit": _LIMIT})},
    {"name": "state_stats",
     "description": "Per employer state: visa employers, how many have linked WHD cases, the share, "
                    "cases, cases per 100 employers, back wages, penalties and visa-program violations.",
     "input_schema": _schema({"program": _PROGRAM, "visa_violations_only": _VISA_ONLY,
                              "sort_by": {"type": "string", "enum": GROUP_SORTS}, "limit": _LIMIT})},
    {"name": "industry_stats",
     "description": "The same numbers as state_stats, per NAICS industry sector.",
     "input_schema": _schema({"program": _PROGRAM, "visa_violations_only": _VISA_ONLY,
                              "sort_by": {"type": "string", "enum": GROUP_SORTS}, "limit": _LIMIT})},
    {"name": "data_overview",
     "description": "Totals for the whole database: employers, applications, employers with linked "
                    "cases, cases, back wages and penalties.",
     "input_schema": _schema({})},
]


def _limit(args, default=10):
    return max(1, min(int(args.get("limit") or default), MAX_ROWS))


def _money(x):
    return round(x or 0, 2)


def search_employers(con, args):
    hits = q.search_employers(con, args["query"], limit=10)
    return {"matches": [{k: h[k] for k in ("employer_id", "employer_name", "dba", "program", "city", "state",
                                           "fein", "n_applications", "n_cases", "willful_violator", "willful_yes")}
                        for h in hits]}


def get_employer(con, args):
    eid = int(args["employer_id"])
    e = q.employer(con, eid)
    if not e:
        raise LookupError(f"No employer with id {eid}")
    keep = ("employer_id", "program", "employer_name", "dba", "address", "city", "state", "zip5", "fein",
            "naics", "visa_classes", "n_applications", "n_certified", "h1b_dependent", "willful_violator",
            "willful_yes")
    cases = q.cases(con, eid)
    profile = q.employer_profile(con, eid)
    debarred = [{k: d[k] for k in ("program", "entity", "entity_type", "location", "start_date", "end_date",
                                   "status", "violation", "applications_during", "match", "source_url")}
                for d in q.employer_debarments(con, eid)]
    return {
        "employer": {**{k: e.get(k) for k in keep}, "sector": q.SECTORS.get(q.sector_of(e["naics"]))},
        "totals": {k: (_money(v) if k in ("back_wages", "penalties") else v)
                   for k, v in q.summary(con, eid).items()},
        "cases": [{"case_id": v["case_id"], "whd_name": v["trade_nm"] or v["legal_name"],
                   "whd_city": v["cty_nm"], "whd_state": v["st_cd"],
                   "findings_start": (v["findings_start_date"] or "")[:10],
                   "findings_end": (v["findings_end_date"] or "")[:10],
                   "violations": v["case_violtn_cnt"], "back_wages": _money(v["bw_atp_amt"]),
                   "workers_owed": v["ee_violtd_cnt"], "penalties": _money(v["cmp_assd"]),
                   "h1b_violations": v["h1b_violtn_cnt"], "h2b_violations": v["h2b_violtn_cnt"],
                   "laws": [{"law": r["name"], "violations": r["violations"], "back_wages": _money(r["back_wages"]),
                             "workers_owed": r["workers"], "penalties": _money(r["penalties"])}
                            for r in v["laws"]],
                   **{k: (_money(x) if k.endswith("back_wages") else x)
                      for k, x in v["details"].items() if x},
                   "match": q.match_label(v["method"], v["est_false_match_rate"])}
                  for v in cases[:MAX_ROWS]],
        "cases_not_shown": max(0, len(cases) - MAX_ROWS),
        "top_jobs": [{k: j[k] for k in ("soc_title", "applications", "workers")} for j in profile["jobs"][:5]],
        "offered_vs_prevailing_wage": [b for b in profile["wage_bands"] if b["applications"]],
        "same_tax_id_elsewhere": q.same_tax_id(con, eid)[:10],
        "red_flags": [{k: f[k] for k in ("title", "applications", "of", "baseline", "detail")}
                      for f in q.red_flags(con, eid)],
        "dol_debarments": debarred,
    }


_APP_KEEP = ("case_number", "case_status", "visa_class", "decision_date", "job_title", "soc_title", "workers",
             "worksite_city", "worksite_state", "wage_from", "wage_to", "wage_unit", "prevailing_wage",
             "pw_unit_of_pay", "pw_wage_level", "lawfirm")


def list_applications(con, args):
    eid = int(args["employer_id"])
    e = q.employer(con, eid)
    if not e:
        raise LookupError(f"No employer with id {eid}")
    apps = q.applications(con, eid, limit=_limit(args))
    return {"employer_id": eid, "total_applications": e["n_applications"],
            "applications": [{k: a.get(k) for k in _APP_KEEP} for a in apps]}


def get_application(con, args):
    a = q.application(con, args["case_number"])
    if not a:
        raise LookupError(f"No application with case number {args['case_number']!r}")
    h = q.application_highlights(a)
    return {"case_number": a["case_number"], "program": a["program"], "case_status": a.get("case_status"),
            "visa_class": a.get("visa_class"), "decision_date": a.get("decision_date"),
            "employer_id": a["employer_id"], "employer_name": a["employer_row_name"],
            "employer_city": a["employer_row_city"], "employer_state": a["employer_row_state"],
            **{k: v for k, v in h.items() if v is not None}}


def watchlist(con, args):
    filters = dict(program=args.get("program"), state=(args.get("state") or "").upper() or None,
                   sector=args.get("sector"), since_year=args.get("since_year"),
                   visa_violations_only=bool(args.get("visa_violations_only")),
                   min_applications=int(args.get("min_applications") or 1))
    rows = q.watchlist(con, **filters)
    for r in rows:
        r["visa_violations"] = r["h1b_violations"] if r["program"] == "H-1B" else r["h2b_violations"]
    key = args.get("sort_by") or "back_wages"
    if key not in WATCHLIST_SORTS:
        raise ValueError(f"sort_by must be one of {WATCHLIST_SORTS}")
    rows.sort(key=lambda r: (-(r[key] or 0), r["employer_id"]))
    totals = q.watchlist_totals(con, **filters)
    keep = ("employer_id", "employer_name", "program", "city", "state", "n_applications", "n_cases",
            "violations", "visa_violations", "back_wages", "workers", "penalties", "latest_case")
    return {"filters": {k: v for k, v in filters.items() if v}, "sorted_by": key,
            "employers": len(rows), "cases": totals["cases"], "back_wages": _money(totals["back_wages"]),
            "penalties": _money(totals["penalties"]),
            "rows": [{k: (_money(r[k]) if k in ("back_wages", "penalties") else r[k]) for k in keep}
                     for r in rows[:_limit(args)]]}


def _group(con, args, fn, name_key):
    rows = fn(con, program=args.get("program"), visa_violations_only=bool(args.get("visa_violations_only")))
    key = args.get("sort_by") or "employers"
    if key not in GROUP_SORTS:
        raise ValueError(f"sort_by must be one of {GROUP_SORTS}")
    rows.sort(key=lambda r: -(r[key] or 0))
    return {"sorted_by": key, "groups": len(rows),
            "rows": [{**{k: r[k] for k in (name_key, "employers", "employers_with_cases", "cases", "visa_violations")},
                      "share_with_cases": round(r["share_with_cases"], 4),
                      "cases_per_100": round(r["cases_per_100"], 2),
                      "back_wages": _money(r["back_wages"]), "penalties": _money(r["penalties"])}
                     for r in rows[:_limit(args)]]}


def state_stats(con, args):
    return _group(con, args, q.state_stats, "state")


def industry_stats(con, args):
    out = _group(con, args, q.sector_stats, "name")
    for r in out["rows"]:
        r["industry"] = r.pop("name")
    return out


def data_overview(con, args):
    t = q.overview(con)["totals"]
    return {k: (_money(v) if k in ("back_wages", "penalties") else v) for k, v in t.items()}


RUNNERS = {t["name"]: globals()[t["name"]] for t in TOOLS}


def run_tool(con, name, args):
    """Run one tool; raises KeyError for an unknown tool and LookupError/ValueError for bad input."""
    return RUNNERS[name](con, args or {})

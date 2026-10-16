"""Score the chat on questions whose answers are worked out straight from the database.

Run from the repo root (needs ANTHROPIC_API_KEY; each run costs money, so it is not part of the unit tests):

    python3 -m chat.eval --out chat-eval.json

`build_cases` writes about 40 questions from the current database, so the expected answers move
with the data. `grade` checks an answer three ways: the expected numbers appear, the records that
answer the question are cited, and no citation points at an ID the tools never returned.
"""
import argparse, json, re, sys, time

from . import engine
from .tools import q, run_tool

# A number with optional $, thousands commas, decimals and a K/M/B or thousand/million/billion suffix.
_NUM = re.compile(r"\$?(\d[\d,]*(?:\.\d+)?)\s*(k|m|b|thousand|million|billion)?\b", re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
NO_DATA_WORDS = ("not in the data", "doesn't cover", "does not cover", "doesn't include", "does not include",
                 "no data", "not available", "don't have", "do not have", "isn't in", "is not in", "can't answer",
                 "cannot answer", "not covered", "doesn't contain", "does not contain")


def numbers_in(text):
    """Each number stated in `text` as (value, rounding), where rounding is half a unit of the last digit
    shown: "$3.3 million" is 3,300,000 give or take 50,000."""
    out = []
    for m in _NUM.finditer(text):
        digits, scale = m.group(1).replace(",", ""), _SCALE.get((m.group(2) or "").lower(), 1)
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        out.append((float(digits) * scale, 0.5 * 10 ** -decimals * scale))
    return out


def has_number(text, want, rel=0.01):
    """True when `text` states `want`, allowing 1% or the rounding of the number as shown."""
    for got, rounding in numbers_in(text):
        if abs(got - want) <= max(abs(want) * rel, rounding):
            return True
    return False


def has_percent(text, share):
    return any(abs(got - 100 * share) <= max(0.15, rounding) for got, rounding in numbers_in(text))


def grade(case, result):
    """Pass/fail per check, and whether the whole case passed."""
    text = result["raw"]
    checks = {"no_unverified_citations": not result["unverified"]}
    for n in case.get("numbers", []):
        checks[f"number {n:g}"] = has_number(text, n)
    for p in case.get("percents", []):
        checks[f"percent {100 * p:.1f}%"] = has_percent(text, p)
    cited = {(c["kind"], c["id"]) for c in result["citations"] if c["verified"]}
    for kind, ident in case.get("cites", []):
        checks[f"cites {kind} {ident}"] = (kind, str(ident)) in cited
    for word in case.get("mentions", []):
        checks[f"mentions {word}"] = word.lower() in text.lower()
    if case.get("no_data"):
        checks["says the data doesn't cover it"] = any(w in text.lower() for w in NO_DATA_WORDS)
    return {"checks": checks, "passed": all(checks.values())}


def _wl(con, **args):
    return run_tool(con, "watchlist", args)


def build_cases(con):
    """About 40 questions with expected answers, from the database as it is now."""
    cases = []
    add = lambda kind, question, **expect: cases.append({"id": f"{kind}-{len(cases) + 1:02d}", "kind": kind,
                                                         "question": question, **expect})
    top = _wl(con, limit=6)["rows"]
    # One employer's linked cases and back wages.
    for r in top[:6]:
        add("employer", f"How many Wage and Hour cases are linked to {r['employer_name']} in {r['city']}, "
            f"{r['state']}, and how much in back wages did they find?",
            numbers=[r["n_cases"], r["back_wages"]], cites=[("employer", str(r["employer_id"]))])
    # Top employer by back wages, per program and state.
    for program, state in [("H-2B", "TX"), ("H-2B", "FL"), ("H-1B", "CA"), ("H-1B", "NJ"), ("H-2B", "LA"),
                           ("H-1B", "TX")]:
        rows = _wl(con, program=program, state=state, limit=1)["rows"]
        if rows:
            r = rows[0]
            add("ranking", f"Which {program} employer in {state} has the most back wages in its linked "
                "Wage and Hour cases, and how much?",
                numbers=[r["back_wages"]], cites=[("employer", str(r["employer_id"]))])
    # Visa-program violations for well-known filers.
    for r in _wl(con, visa_violations_only=True, sort_by="n_applications", limit=5)["rows"]:
        add("visa", f"Did {r['employer_name']} ({r['city']}, {r['state']}) have any {r['program']} violations? "
            "How many, and in which cases?",
            numbers=[r["visa_violations"]], cites=[("employer", str(r["employer_id"]))])
    # Counts across employers.
    for program in ("H-1B", "H-2B"):
        w = _wl(con, program=program, visa_violations_only=True, limit=1)
        add("count", f"How many {program} employers had Wage and Hour cases that found {program} violations?",
            numbers=[w["employers"]])
    w = _wl(con, since_year=2020, limit=1)
    add("count", "How many visa employers have linked Wage and Hour cases that ended in 2020 or later?",
        numbers=[w["employers"]])
    # Application details.
    apps = q.rows(con, """SELECT case_number FROM applications WHERE program = ? AND prevailing_wage > 0
                          ORDER BY case_number LIMIT 3""", "H-1B")
    apps += q.rows(con, """SELECT case_number FROM applications WHERE program = ? AND basic_wage_rate_from > 0
                           ORDER BY case_number LIMIT 2""", "H-2B")
    for a in apps:
        d = run_tool(con, "get_application", {"case_number": a["case_number"]})
        nums = [d[k] for k in ("wage_from", "prevailing_wage") if d.get(k)]
        add("application", f"What wage does application {d['case_number']} offer, and what is the prevailing "
            "wage for that job?", numbers=nums, cites=[("application", d["case_number"])])
    # States and industries.
    for sort, label in [("cases", "the most linked Wage and Hour cases"), ("back_wages", "the most back wages")]:
        r = run_tool(con, "state_stats", {"sort_by": sort, "limit": 1})["rows"][0]
        add("state", f"Which employer state has {label} among visa employers?",
            mentions=[r["state"]], numbers=[r[sort]])
    for st in ("TX", "CA", "NY"):
        r = next(x for x in q.state_stats(con) if x["state"] == st)
        add("state", f"What share of visa employers in {st} have a linked Wage and Hour case?",
            percents=[r["share_with_cases"]])
    rows = [r for r in q.sector_stats(con) if r["employers"] >= 100]
    rows.sort(key=lambda r: -r["share_with_cases"])
    if rows:
        add("industry", "Among industries with at least 100 visa employers, which has the highest share of "
            "employers with a linked Wage and Hour case?", mentions=[rows[0]["name"].split(",")[0]],
            percents=[rows[0]["share_with_cases"]])
    for r in sorted(q.sector_stats(con), key=lambda r: -r["employers"])[:3]:
        add("industry", f"How many visa employers are in the {r['name']} industry, and how many of them "
            "have linked Wage and Hour cases?", numbers=[r["employers"], r["employers_with_cases"]])
    # Totals.
    t = run_tool(con, "data_overview", {})
    add("total", "How many employers and visa applications are in the data?",
        numbers=[t["employers"], t["applications"]])
    add("total", "How much in back wages have the Wage and Hour cases linked to visa employers found in total?",
        numbers=[t["back_wages"]])
    # The willful violator answer is self-reported.
    e = run_tool(con, "get_employer", {"employer_id": 61603})["employer"] if q.employer(con, 61603) else None
    if e:
        add("willful", f"Is {e['employer_name']} ({e['city']}, {e['state']}) a willful violator?",
            numbers=[e["willful_yes"]], cites=[("employer", "61603")])
    # Questions the data cannot answer.
    for question in ["What was Infosys's revenue last year?",
                     "Which employers will be investigated by the Department of Labor next year?",
                     "How many H-1B workers does Microsoft employ in total right now?",
                     "What are the H-1B filings for fiscal year 2019?"]:
        add("no_data", question, no_data=True)
    return cases


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="chat-eval.json", help="where to write every question, answer and check")
    ap.add_argument("--model", default=engine.MODEL)
    ap.add_argument("--effort", choices=["low", "medium", "high"])
    ap.add_argument("--only", help="run only cases whose id starts with this (for example 'visa')")
    ap.add_argument("--list", action="store_true", help="print the questions and expected answers, no API calls")
    a = ap.parse_args(argv)
    con = q.connect()
    cases = [c for c in build_cases(con) if not a.only or c["id"].startswith(a.only)]
    if a.list:
        print(json.dumps(cases, indent=2, default=str))
        return 0
    report, cost, passed = [], 0.0, 0
    for c in cases:
        t0 = time.time()
        r = engine.answer(con, c["question"], model=a.model, effort=a.effort)
        g = grade(c, r)
        cost += r["cost_usd"]
        passed += g["passed"]
        report.append({**c, **g, "answer": r["raw"], "tool_calls": r["tool_calls"], "cost_usd": r["cost_usd"],
                       "seconds": round(time.time() - t0, 1)})
        print(f"{'PASS' if g['passed'] else 'FAIL'} {c['id']} ${r['cost_usd']:.4f}  "
              + ", ".join(k for k, ok in g["checks"].items() if not ok), file=sys.stderr)
    summary = {"model": a.model, "effort": a.effort, "cases": len(cases), "passed": passed,
               "cost_usd": round(cost, 4), "cost_per_question_usd": round(cost / max(len(cases), 1), 5)}
    with open(a.out, "w") as f:
        json.dump({"summary": summary, "cases": report}, f, indent=2, default=str)
    print(json.dumps(summary, indent=2))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

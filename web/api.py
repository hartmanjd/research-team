"""JSON API over research.db for the dashboard website, and the site's static files.

Run from the repo root:  uvicorn web.api:app
Then open http://localhost:8000. Reads h1b-data/research.db (or RESEARCH_DB), read-only, and
downloads it on first start if it is missing (see dashboard/queries.py).
"""
import os, sys
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dashboard"))
import queries as q  # noqa: E402

PAGE_SIZE = 100


@asynccontextmanager
async def lifespan(app):
    q.download_db()  # no-op when the database is already there
    yield


app = FastAPI(title="H-1B / H-2B employer research API", lifespan=lifespan)


def con():
    """A fresh read-only connection per request; opening one takes about a millisecond."""
    return q.connect()


def check_program(program):
    if program not in (None, "", "H-1B", "H-2B"):
        raise HTTPException(422, "program must be H-1B or H-2B")


@lru_cache(maxsize=16)
def _group_stats(kind, program, visa_only):
    """State and sector totals scan every match, so each filter combination is computed once.

    Safe to cache because the database is opened read-only and does not change while the app runs.
    """
    c = con()
    try:
        fn = q.state_stats if kind == "states" else q.sector_stats
        return fn(c, program=program, visa_violations_only=visa_only)
    finally:
        c.close()


@app.get("/api/states")
def states(program: str | None = None, visa_only: bool = False):
    """Per-state visa employers and linked WHD case totals, for the map."""
    check_program(program)
    return _group_stats("states", program or None, visa_only)


@app.get("/api/sectors")
def sectors(program: str | None = None, visa_only: bool = False):
    """Per-NAICS-sector visa employers and linked WHD case totals, for the Industries page."""
    check_program(program)
    return _group_stats("sectors", program or None, visa_only)


@app.get("/api/meta")
def meta():
    c = con()
    try:
        return {"states": q.states(c), "sectors": q.SECTORS, "sources": q.sources(c)}
    finally:
        c.close()


@app.get("/api/search")
def search(q_: str = Query("", alias="q")):
    """Employers by name, trade name or tax ID. A DOL case number returns that application's
    employer, with the case number, so the page can open the application."""
    c = con()
    try:
        hit = q.find_application(c, q_)
        if hit:
            return [dict(r, case_number=hit["case_number"])
                    for r in q.search_employers_by_id(c, hit["employer_id"])]
        return q.search_employers(c, q_)
    finally:
        c.close()


@app.get("/api/employers/{employer_id}")
def employer(employer_id: int):
    """Everything the employer page shows except the application list, which is paged."""
    c = con()
    try:
        e = q.employer(c, employer_id)
        if not e:
            raise HTTPException(404, "No employer with that id")
        cases = q.cases(c, employer_id)
        for v in cases:
            v["match_label"] = q.match_label(v["method"], v["est_false_match_rate"])
        e["sector"] = q.sector_of(e["naics"])
        e["sector_name"] = q.SECTORS.get(e["sector"])
        return {"employer": e, "summary": q.summary(c, employer_id),
                "same_tax_id": q.same_tax_id(c, employer_id), "cases": cases,
                "case_years": q.case_years(c, employer_id), "profile": q.employer_profile(c, employer_id)}
    finally:
        c.close()


@app.get("/api/employers/{employer_id}/applications")
def applications(employer_id: int, page: int = Query(1, ge=1)):
    c = con()
    try:
        if not q.employer(c, employer_id):
            raise HTTPException(404, "No employer with that id")
        apps = q.applications(c, employer_id)
        start = (page - 1) * PAGE_SIZE
        return {"total": len(apps), "page": page, "page_size": PAGE_SIZE,
                "rows": apps[start:start + PAGE_SIZE]}
    finally:
        c.close()


@app.get("/api/applications/{case_number}")
def application(case_number: str):
    """One application with every column of its DOL disclosure record, grouped for display."""
    c = con()
    try:
        a = q.application(c, case_number)
        if not a:
            raise HTTPException(404, "No application with that case number")
        return {"application": {k: a[k] for k in ("case_number", "program", "employer_id", "case_status",
                                                  "visa_class", "source_file", "table_file", "table_sha256",
                                                  "dol_file_url", "employer_row_name", "employer_row_city",
                                                  "employer_row_state")},
                "highlights": q.application_highlights(a), "sections": q.application_sections(a)}
    finally:
        c.close()


@app.get("/api/watchlist")
def watchlist(program: str | None = None, state: str | None = None,
              since: int | None = Query(None, ge=1900, le=2100), visa_only: bool = False,
              min_apps: int = Query(1, ge=1), sector: str | None = None):
    check_program(program)
    if sector and sector not in q.SECTORS:
        raise HTTPException(422, "Unknown sector")
    filters = dict(program=program or None, state=state or None, since_year=since,
                   visa_violations_only=visa_only, min_applications=min_apps, sector=sector or None)
    c = con()
    try:
        return {"rows": q.watchlist(c, **filters), "totals": q.watchlist_totals(c, **filters)}
    finally:
        c.close()


app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True), name="static")

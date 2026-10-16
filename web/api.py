"""JSON API over research.db for the dashboard website, and the site's static files.

Run from the repo root:  uvicorn web.api:app
Then open http://localhost:8000. Reads h1b-data/research.db (or RESEARCH_DB), read-only, and
downloads it on first start if it is missing (see dashboard/queries.py).
"""
import os, sys
from contextlib import asynccontextmanager

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


@app.get("/api/meta")
def meta():
    c = con()
    try:
        return {"states": q.states(c), "sources": q.sources(c)}
    finally:
        c.close()


@app.get("/api/search")
def search(q_: str = Query("", alias="q")):
    c = con()
    try:
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
        return {"employer": e, "summary": q.summary(c, employer_id),
                "same_tax_id": q.same_tax_id(c, employer_id), "cases": cases}
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


@app.get("/api/watchlist")
def watchlist(program: str | None = None, state: str | None = None,
              since: int | None = Query(None, ge=1900, le=2100), visa_only: bool = False,
              min_apps: int = Query(1, ge=1)):
    if program not in (None, "", "H-1B", "H-2B"):
        raise HTTPException(422, "program must be H-1B or H-2B")
    filters = dict(program=program or None, state=state or None, since_year=since,
                   visa_violations_only=visa_only, min_applications=min_apps)
    c = con()
    try:
        return {"rows": q.watchlist(c, **filters), "totals": q.watchlist_totals(c, **filters)}
    finally:
        c.close()


app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True), name="static")

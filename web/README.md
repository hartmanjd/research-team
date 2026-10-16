# Visa Employer Watch (website)

A designed website over `h1b-data/research.db`: a small JSON API (`api.py`, built with FastAPI) and a
hand-written front end (`static/`) with no build step. It has Employer lookup, an employer page for each
employer, a page for each visa application, the Watchlist, a state Map and an Industries view. The database is
opened read-only and is downloaded on first start if it is missing (see `dashboard/README.md`).

## Run it

From the repo root, with the virtual environment active (see `dashboard/README.md`):

    pip install -r requirements.txt
    uvicorn web.api:app --reload

Then open http://localhost:8000 in a browser. `--reload` restarts the server when a file changes.

## Pages

| Address | Page |
| --- | --- |
| `#/` | Employer lookup: search by name, trade name (DBA) or tax ID, or open an application by its DOL case number |
| `#/employer/<id>` | One employer: DOL flags, totals, linked cases by year, same tax ID elsewhere, its jobs, worksites, offered against prevailing wages and representatives, each linked WHD case with its match rule and source, and its visa applications |
| `#/application/<case number>` | One application: headline job, workers, wages and dates, then every field of its DOL disclosure record by section |
| `#/watchlist` | Every employer with linked WHD cases, sortable, with filters (program, state, industry, year, visa violations, applications) kept in the address |
| `#/map` | A tile map of states colored by cases per 100 visa employers, share with a case, back wages or case count, with top-state bars and a table |
| `#/industries` | NAICS sectors: a size-against-rate bubble chart, bars for share with a case and back wages, and a table |

On the Map and Industries pages, hovering a state or industry shows its numbers, and clicking it opens
the Watchlist filtered to it.

## API

| Endpoint | Returns |
| --- | --- |
| `GET /api/search?q=` | Up to 50 employers matching a name or tax ID; for a DOL case number, the employer that filed it, with the case number |
| `GET /api/employers/{id}` | The employer, its totals, other rows with the same tax ID, its linked WHD cases by year and in full, and a profile of its applications (jobs, worksites, law firms, attorneys, offered against prevailing wage) |
| `GET /api/employers/{id}/applications?page=` | Its visa applications, newest decision first, 100 per page, with job, worksite, wages, law firm and a link to each DOL file |
| `GET /api/applications/{case_number}` | One application: headline numbers and every disclosure field, grouped into sections |
| `GET /api/watchlist?program=&state=&sector=&since=&visa_only=&min_apps=` | Watchlist rows plus totals that count each case once |
| `GET /api/states?program=&visa_only=` | Per state: visa employers, applications, employers with a case, cases, back wages, penalties, visa violations and rates |
| `GET /api/sectors?program=&visa_only=` | The same numbers per NAICS sector |
| `GET /api/meta` | States, NAICS sector names and the source files behind the database |

FastAPI also serves interactive API docs at http://localhost:8000/docs.

## Hosting

`render.yaml` at the repo root describes the site for [Render](https://render.com). In Render, choose
**New > Blueprint**, pick this repository, and confirm. The free plan sleeps after about 15 minutes
without visitors, so the first visit after that takes 30 to 60 seconds while it wakes and downloads the
database.

## Files

| File | What it is |
| --- | --- |
| api.py | The API and static file server; reuses the lookups in `dashboard/queries.py` |
| static/index.html | Page shell: top bar, navigation, fonts |
| static/styles.css | Design: colors (light and dark), type, cards, tables, filters |
| static/app.js | Routing, the six views and their charts, fetching from the API |
| tests/test_api.py | API tests on a small made-up database |

Run the tests from the repo root with `python3 -m unittest discover web/tests`.

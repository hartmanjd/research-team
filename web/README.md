# Visa Employer Watch (website)

A designed website over `h1b-data/research.db`: a small JSON API (`api.py`, built with FastAPI) and a
hand-written front end (`static/`) with no build step. It has the same two views as the Streamlit
dashboard, Employer lookup and Watchlist, plus an employer page for each employer. The database is
opened read-only and is downloaded on first start if it is missing (see `dashboard/README.md`).

## Run it

From the repo root, with the virtual environment active (see `dashboard/README.md`):

    pip install -r requirements.txt
    uvicorn web.api:app --reload

Then open http://localhost:8000 in a browser. `--reload` restarts the server when a file changes.

## Pages

| Address | Page |
| --- | --- |
| `#/` | Employer lookup: search by name or trade name (DBA) |
| `#/employer/<id>` | One employer: DOL flags, totals, same tax ID elsewhere, each linked WHD case with its match rule and source, and its visa applications |
| `#/watchlist` | Every employer with linked WHD cases, sortable, with filters kept in the address |

## API

| Endpoint | Returns |
| --- | --- |
| `GET /api/search?q=` | Up to 50 employers matching a name |
| `GET /api/employers/{id}` | The employer, its totals, other rows with the same tax ID, and its linked WHD cases |
| `GET /api/employers/{id}/applications?page=` | Its visa applications, 100 per page, with a link to each DOL file |
| `GET /api/watchlist?program=&state=&since=&visa_only=&min_apps=` | Watchlist rows plus totals that count each case once |
| `GET /api/meta` | States and the source files behind the database |

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
| static/app.js | Routing and the three views, fetching from the API |
| tests/test_api.py | API tests on a small made-up database |

Run the tests from the repo root with `python3 -m unittest discover web/tests`.

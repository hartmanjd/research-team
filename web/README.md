# Visa Employer Watch (website)

A designed website over `h1b-data/research.db`: a small JSON API (`api.py`, built with FastAPI) and a
hand-written front end (`static/`) with no build step. It has Employer lookup, an employer page for each
employer, a page for each visa application, the Watchlist, a state Map and an Industries view. The database is
opened read-only and is downloaded on first start if it is missing (see Run it).

## Run it

From the repo root:

1. Make a virtual environment (a private set of Python libraries for this project) and install the requirements:

        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt

   In a new terminal, run `source .venv/bin/activate` again before starting the site.

2. Start the server:

        uvicorn web.api:app --reload

   Then open http://localhost:8000 in a browser. `--reload` restarts the server when a file changes.

The site reads `h1b-data/research.db`. If that file is missing, it downloads a gzipped copy (about 211 MB) from
the repo's `data-2026-10-16` release on first start, checks its SHA-256 and unpacks it there. To use your own
build instead, run `h1b-data/scripts/build_db.py` (see `h1b-data/README.md`) or copy a `research.db` into
`h1b-data/` before starting.

Settings (environment variables, all optional):

| Variable | What it does |
| --- | --- |
| RESEARCH_DB | Path of the database to use instead of `h1b-data/research.db` |
| RESEARCH_DB_URL | Where to download the gzipped database from instead of the release |
| RESEARCH_DB_SHA256 | Checksum of the file at RESEARCH_DB_URL |

## Pages

| Address | Page |
| --- | --- |
| `#/` | Employer lookup: search by name, trade name (DBA) or tax ID, or open an application by its DOL case number. Before a search it shows a small map of cases per 100 visa employers, headline totals and three starting points: the employers with the most back wages, employers whose WHD cases found violations of their own visa program and that still filed in FY2025, and the industries with the highest share of employers with a case |
| `#/employer/<id>` | One employer: DOL flags, totals, linked cases by year, same tax ID elsewhere, its jobs, worksites, offered against prevailing wages and representatives, each linked WHD case with its match rule and source, and its visa applications |
| `#/application/<case number>` | One application: headline job, workers, wages and dates, then every field of its DOL disclosure record by section |
| `#/watchlist` | Every employer with linked WHD cases, sortable, with filters (program, state, industry, year, visa violations, applications) kept in the address |
| `#/map` | A tile map of states colored by cases per 100 visa employers, share with a case, back wages or case count, with top-state bars and a table |
| `#/industries` | NAICS sectors: a size-against-rate bubble chart, bars for share with a case and back wages, and a table |

On the Map and Industries pages, hovering a state or industry shows its numbers, and clicking it opens
the Watchlist filtered to it.

The footer on every page has a "Use this data with AI (MCP)" section with the MCP server's address and the
steps for adding it to Claude. `static/llms.txt`, served at `/llms.txt`, is a plain-text guide for AI tools
that lists the MCP address, its tools, what the data means and which pages to cite.

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
| `GET /api/overview` | Headline totals and the lookup page's starting points (computed once per server start) |
| `GET /api/meta` | States, NAICS sector names and the source files behind the database |
| `POST /mcp` | The chat's eight lookups as a read-only MCP server (see `chat/README.md` for connecting Claude Desktop) |

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

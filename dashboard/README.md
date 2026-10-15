# Employer dashboard

A Streamlit app over `h1b-data/research.db`, opened read-only. It has two pages, chosen in the sidebar:

- **Employer lookup:** search for an H-1B or H-2B employer and see its visa applications, the Wage and Hour (WHD) enforcement cases linked to it, how each case was linked, and the DOL file every number came from.
- **Watchlist:** every visa employer with linked WHD cases in one sortable table, filtered by program, state, case date, number of applications and visa-program violations. Clicking a row opens that employer. The filters are kept in the address bar, so a filtered list can be bookmarked or shared.

## Run it

From the repo root:

1. Make a virtual environment (a private set of Python libraries for this project) and install the requirements:

        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt

   In a new terminal, run `source .venv/bin/activate` again before starting the app.

2. Start the app:

        streamlit run dashboard/app.py

   Streamlit prints a local address (usually http://localhost:8501); open it in a browser.

The app reads `h1b-data/research.db`. If that file is missing, it downloads a gzipped copy (about 55 MB) from the repo's `data-2026-10-15` release on first start, checks its SHA-256 and unpacks it there. To use your own build instead, run `h1b-data/scripts/build_db.py` (see `h1b-data/README.md`) or copy a `research.db` into `h1b-data/` before starting.

Settings (environment variables, all optional):

| Variable | What it does |
| --- | --- |
| RESEARCH_DB | Path of the database to use instead of `h1b-data/research.db` |
| RESEARCH_DB_URL | Where to download the gzipped database from instead of the release |
| RESEARCH_DB_SHA256 | Checksum of the file at RESEARCH_DB_URL |

## Publishing a new database

After rebuilding `research.db`, gzip it (`gzip -k h1b-data/research.db`), upload `research.db.gz` to a new GitHub release, and update `DB_URL` and `DB_SHA256` in `queries.py` (`sha256sum h1b-data/research.db.gz` gives the checksum).

## Files

| File | What it is |
| --- | --- |
| app.py | The Streamlit pages: Employer lookup, Watchlist, and one page per employer |
| queries.py | The database lookups the page uses (plain Python, no Streamlit) |
| tests/test_queries.py | Tests for the lookups on a small made-up database |

Run the tests from the repo root with `python3 -m unittest discover dashboard/tests`.

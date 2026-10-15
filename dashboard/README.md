# Employer dashboard

A Streamlit app for looking up an H-1B or H-2B employer in `h1b-data/research.db`: its visa applications, the Wage and Hour (WHD) enforcement cases linked to it, how each case was linked, and the DOL file every number came from. The database is opened read-only.

## Run it

1. Build the database first (see `h1b-data/README.md`), or copy an existing `research.db` into `h1b-data/`.
2. Install the requirements, from the repo root:

        pip install -r requirements.txt

3. Start the app, from the repo root:

        streamlit run dashboard/app.py

   Streamlit prints a local address (usually http://localhost:8501); open it in a browser.

To use a database somewhere else, set `RESEARCH_DB` first, e.g. `RESEARCH_DB=/path/to/research.db streamlit run dashboard/app.py`.

## Files

| File | What it is |
| --- | --- |
| app.py | The Streamlit page: search, then one page per employer |
| queries.py | The database lookups the page uses (plain Python, no Streamlit) |
| tests/test_queries.py | Tests for the lookups on a small made-up database |

Run the tests from the repo root with `python3 -m unittest discover dashboard/tests`.

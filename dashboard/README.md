# Database lookups

`queries.py` holds every lookup the website (`web/`) makes against `h1b-data/research.db`, as plain Python
functions with no web code, so they can be tested on their own. The database is opened read-only. If it is
missing, `download_db` fetches the gzipped copy from the GitHub release named in `DB_URL` and checks it
against `DB_SHA256`.

## Publishing a new database

After rebuilding `research.db`, gzip it (`gzip -k h1b-data/research.db`), upload `research.db.gz` to a new GitHub
release, and update `DB_URL` and `DB_SHA256` in `queries.py` (`sha256sum h1b-data/research.db.gz` gives the
checksum).

## Files

| File | What it is |
| --- | --- |
| queries.py | The database lookups: search, employer pages, applications, Watchlist, state and industry stats, the home page overview |
| tests/test_queries.py | Tests for the lookups on a small made-up database |

Run the tests from the repo root with `python3 -m unittest discover dashboard/tests`.

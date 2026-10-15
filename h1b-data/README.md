# H-1B / H-2B data check

Scripts and results from the FY2025 feasibility check (2026-10-15): can DOL Wage and Hour (WHD) violation cases be linked to H-1B and H-2B employers?

The two employer tables (`filers_*_fy2025.csv`, about 12 MB) and all raw downloads are not in git; rebuild them with the scripts below. Needs Python 3 with pandas.

| File | What it is |
| --- | --- |
| filers_lca_fy2025.csv (not in git) | One row per H-1B (LCA) employer: cleaned name, state, ZIP, tax ID, counts, willful-violator flag |
| filers_h2b_fy2025.csv (not in git) | Same for H-2B employers |
| name_match_benchmark.csv | How well name rules re-find the 144 employers in both programs, using tax ID as the answer key |
| scripts/employer_keys.py | Name cleaning and ZIP/tax ID helpers |
| scripts/build_filers.py | Turns the raw disclosure files (converted to CSV) into the employer tables |
| scripts/name_match_benchmark.py | Produces name_match_benchmark.csv |
| scripts/fetch_whd.py | Downloads WHD enforcement data (key from env var DOL_API_KEY, sent in the URL). 2,000 rows a page, backs off on rate limits, re-run with the same output file to resume |
| scripts/match_whd.py | Match rates of WHD H-1B/H-2B violation cases to filers |
| whd_match_rates.csv | Output of match_whd.py (run 2026-10-15 on 370,964 WHD cases) |

To rebuild the employer tables, download the FY2025 LCA (Q1-Q4) and H-2B disclosure files from
https://www.dol.gov/agencies/eta/foreign-labor/performance, convert each sheet to CSV, then:

    python3 scripts/build_filers.py filers_lca_fy2025.csv LCA_Q1.csv LCA_Q2.csv LCA_Q3.csv LCA_Q4.csv
    python3 scripts/build_filers.py filers_h2b_fy2025.csv H2B_FY2025.csv

To re-run the WHD match (raw download about 70 MB and 25 minutes; key in env var DOL_API_KEY):

    python3 scripts/fetch_whd.py /tmp/whd.csv
    python3 scripts/match_whd.py /tmp/whd.csv filers_lca_fy2025.csv filers_h2b_fy2025.csv .

"""Turn DOL's published debarment lists into one CSV: h1b-data/debarments.csv.

Debarment is DOL's own enforcement finding: a debarred employer, agent or labor contractor may not
use the program for the period shown. Three DOL sources are combined:

  * OFLC's Program Debarments PDF (PERM, H-2A and H-2B lists), from
    https://www.dol.gov/agencies/eta/foreign-labor/program-debarments
  * WHD's current H-1B list, the table on https://www.dol.gov/agencies/whd/immigration/h1b/debarment
    (save the page as HTML)
  * WHD's older H-1B workbook, H1BDebarmentList.xls, linked from that page

dol.gov blocks scripted downloads, so save the three files with a web browser, then run:

    python3 h1b-data/scripts/parse_debarments.py Debarment_List.pdf debarment.html H1BDebarmentList.xls

Needs pdfplumber and xlrd (pip install pdfplumber xlrd); the website itself needs neither.
Every row keeps its source URL and file, and a manifest records the inputs' checksums.
"""
import argparse, csv, datetime, html, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from employer_keys import clean_name  # noqa: E402
from provenance import write_manifest  # noqa: E402

OUT = os.path.join(HERE, "..", "debarments.csv")
OFLC_URL = "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/Debarment_List.pdf"
H1B_PAGE_URL = "https://www.dol.gov/agencies/whd/immigration/h1b/debarment"
H1B_XLS_URL = "https://www.dol.gov/sites/dolgov/files/WHD/legacy/files/H1BDebarmentList.xls"
FIELDS = ["program", "entity", "entity_type", "location", "state", "start_date", "end_date", "violation",
          "cfr_citation", "willful_violator", "name_clean", "source_url", "source_file"]
PROGRAMS = {"Permanent Labor Certification": "PERM", "H-2A": "H-2A", "H-2B": "H-2B"}
STATES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
          "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
          "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
          "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
          "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
          "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
          "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
          "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
          "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
          "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY", "Puerto Rico": "PR", "Guam": "GU"}


def one_line(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def state_of(location):
    """Two-letter state from 'City, State' or 'City, ST'; '' when there is none."""
    last = one_line(location).split(",")[-1].strip()
    if last.upper() in STATES.values():
        return last.upper()
    return STATES.get(last, "")


def iso_date(s):
    """'May 29, 2025', 'July,10, 2030', 'September 28 2027' or '5/12/2025' as 2025-05-29.
    'Permanent' stays 'permanent', and a blank stays blank."""
    s = one_line(s).replace(",", " ").replace(". ", " ")
    if s.lower() in ("", "permanent"):
        return s.lower()
    for fmt in ("%B %d %Y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(" ".join(s.split()), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unreadable date: {s!r}")


def row(program, entity, source_url, source_file, **kw):
    entity = one_line(entity).rstrip("*^").strip()  # footnote marks in DOL's list
    r = {f: "" for f in FIELDS}
    r.update(program=program, entity=entity, name_clean=clean_name(entity), source_url=source_url,
             source_file=source_file, **kw)
    return r


def parse_oflc_pdf(path):
    """The PERM, H-2A and H-2B tables. Rows split across pages are joined back up."""
    import pdfplumber
    out, program, last = [], None, None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for cells in table:
                    cells = [c or "" for c in cells]
                    title = one_line(cells[0])
                    if title.endswith("Debarment List"):
                        program = next(v for k, v in PROGRAMS.items() if title.startswith(k))
                        last = None
                        continue
                    if title == "Entity":
                        continue
                    if title == "" and not any(c.strip() for c in cells[3:5]):
                        if last is not None and any(c.strip() for c in cells):  # a cell carried onto the next line
                            for i, key in ((0, "entity"), (2, "location"), (5, "violation")):
                                if i < len(cells) and cells[i].strip():
                                    last[key] = one_line(last[key] + " " + cells[i])
                        continue
                    if not cells[3].strip() and not cells[4].strip():  # the rest of an entity name that ran onto a new page
                        if last is not None:
                            last["entity"] = one_line(last["entity"] + " " + cells[0])
                        continue
                    last = {"cells": cells, "program": program, "entity": cells[0], "location": cells[2],
                            "violation": cells[5]}
                    out.append(last)
    rows = []
    for r in out:
        c = r["cells"]
        rows.append(row(r["program"], r["entity"], OFLC_URL, os.path.basename(path), entity_type=one_line(c[1]),
                        location=one_line(r["location"]), state=state_of(r["location"]),
                        # A permanent debarment is written in either date column.
                        start_date=iso_date(c[3]).replace("permanent", ""),
                        end_date="permanent" if "permanent" in (iso_date(c[3]), iso_date(c[4])) else iso_date(c[4]), violation=one_line(r["violation"]),
                        cfr_citation=one_line(c[6]) if len(c) > 6 else ""))
    return rows


def _h1b_row(name, willful, period, source_url, source_file):
    start, end = [p.strip() for p in period.split(" to ")]
    return row("H-1B", name, source_url, source_file, entity_type="Employer", start_date=iso_date(start),
               end_date=iso_date(end), willful_violator="Yes" if willful.strip().upper() == "YES" else "No",
               violation="WHD debarment (H-1B)")


def parse_h1b_page(path):
    """The table on WHD's H-1B debarment page: name, address, willful violator, period."""
    text = open(path, encoding="utf-8", errors="replace").read()
    table = text[text.find("<table"):text.find("</table>")]
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", table, re.S):
        cells = [one_line(html.unescape(re.sub(r"<[^>]+>", " ", td))) for td in re.findall(r"<td.*?</td>", tr, re.S)]
        if len(cells) >= 4 and " to " in cells[3]:
            rows.append(_h1b_row(cells[0], cells[2], cells[3], H1B_PAGE_URL, os.path.basename(path)))
    return rows


def parse_h1b_xls(path):
    import xlrd
    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    return [_h1b_row(str(v[0]), str(v[2]), str(v[3]), H1B_XLS_URL, os.path.basename(path))
            for v in (sheet.row_values(i) for i in range(sheet.nrows)) if " to " in str(v[3])]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("oflc_pdf")
    ap.add_argument("h1b_page")
    ap.add_argument("h1b_xls")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    rows = parse_oflc_pdf(a.oflc_pdf) + parse_h1b_page(a.h1b_page)
    seen = {(r["entity"], r["start_date"]) for r in rows}
    rows += [r for r in parse_h1b_xls(a.h1b_xls) if (r["entity"], r["start_date"]) not in seen]
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    write_manifest(a.out, __file__, inputs=[a.oflc_pdf, a.h1b_page, a.h1b_xls],
                   sources=[{"url": OFLC_URL, "note": "OFLC Program Debarments (PERM, H-2A, H-2B)"},
                            {"url": H1B_PAGE_URL, "note": "WHD H-1B debarred/disqualified employers, current"},
                            {"url": H1B_XLS_URL, "note": "WHD H-1B debarment workbook, older entries"}])
    by = {}
    for r in rows:
        by[r["program"]] = by.get(r["program"], 0) + 1
    print(f"{len(rows)} debarments: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))


if __name__ == "__main__":
    main()

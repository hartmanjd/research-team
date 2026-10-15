"""Shared helpers that turn employer names and ZIPs into matching keys."""
import re

# Legal-form words that differ between filings for the same company.
SUFFIXES = {"INC", "INCORPORATED", "LLC", "L L C", "LLP", "LP", "LTD", "LIMITED", "CORP",
            "CORPORATION", "CO", "COMPANY", "PC", "PLLC", "PA", "THE", "DBA", "GROUP",
            "HOLDINGS", "USA", "US", "AMERICA", "NA", "LC"}


def raw_name(s):
    """Uppercase and trim only: the 'exact name' rule."""
    return re.sub(r"\s+", " ", str(s or "").upper()).strip()


def clean_name(s):
    """Uppercase, '&'->AND, drop punctuation and legal-form words."""
    s = raw_name(s).replace("&", " AND ")
    s = re.sub(r"\bD/?B/?A\b.*$", "", s)  # keep the part before 'DBA ...'
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    words = [w for w in s.split() if w not in SUFFIXES]
    return " ".join(words)


def zip5(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d[:5] if len(d) >= 5 else (d.zfill(5) if len(d) >= 3 else "")


def fein(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d if len(d) == 9 else ""

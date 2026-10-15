"""Provenance manifests: a small JSON record written next to every data file.

For OUT.csv the manifest is OUT.csv.manifest.json. It records the file's
SHA-256 checksum, size and row count, when and by which script (and script
checksum) it was made, the input files it was built from (with their own
checksums), and where the data came from (source URLs). A checksum is a
fingerprint of the file: change one character and it changes, so
verify_manifest() can prove a file is the one that was recorded.
"""
import csv, datetime, hashlib, json, os, sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def count_rows(path):
    """Data rows in a CSV (header excluded; quoted line breaks handled)."""
    csv.field_size_limit(1 << 30)
    with open(path, newline="") as f:
        return max(sum(1 for _ in csv.reader(f)) - 1, 0)


def manifest_path(path):
    return f"{path}.manifest.json"


def describe(path):
    return {"file": os.path.basename(path), "sha256": sha256(path),
            "bytes": os.path.getsize(path), "rows": count_rows(path)}


def write_manifest(path, script, inputs=(), sources=(), params=None):
    """Record PATH's checksum and lineage. Returns the manifest dict.

    script:  __file__ of the script that made PATH.
    inputs:  local files PATH was built from (each gets its own checksum).
    sources: where the data came from, e.g. [{"url": ..., "note": ...}].
    params:  settings that shaped the output (never put secrets here).
    """
    m = describe(path)
    m.update({
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "script": os.path.basename(script), "script_sha256": sha256(script),
        "python": sys.version.split()[0],
        "inputs": [describe(p) for p in inputs],
        "sources": list(sources),
        "params": params or {},
    })
    with open(manifest_path(path), "w") as f:
        json.dump(m, f, indent=2)
        f.write("\n")
    return m


def verify_manifest(path):
    """Raise ValueError if PATH no longer matches its manifest; return the manifest."""
    with open(manifest_path(path)) as f:
        m = json.load(f)
    if sha256(path) != m["sha256"]:
        raise ValueError(f"{os.path.basename(path)} has changed since its manifest was written")
    return m

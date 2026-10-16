"""Ask the chat a question from the command line (needs ANTHROPIC_API_KEY).

Run from the repo root:  python3 -m chat "Which H-2B employers in Texas had the most back wages?"
"""
import argparse, json

from . import engine
from .tools import q


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("question")
    ap.add_argument("--model", default=engine.MODEL)
    ap.add_argument("--effort", choices=["low", "medium", "high"], help="default: the model's own")
    ap.add_argument("--json", action="store_true", help="print the whole result as JSON")
    a = ap.parse_args(argv)
    con = q.connect()
    try:
        r = engine.answer(con, a.question, model=a.model, effort=a.effort)
    finally:
        con.close()
    if a.json:
        print(json.dumps(r, indent=2, default=str))
        return
    print(r["answer"])
    print(f"\n-- {len(r['tool_calls'])} lookups: " + ", ".join(c["name"] for c in r["tool_calls"]))
    if r["unverified"]:
        print("-- unverified citations: " + ", ".join(f"{c['kind']} {c['id']}" for c in r["unverified"]))
    u = r["usage"]
    print(f"-- {u['input_tokens'] + u['cache_read_input_tokens'] + u['cache_creation_input_tokens']:,} tokens in, "
          f"{u['output_tokens']:,} out, about ${r['cost_usd']:.4f}")


if __name__ == "__main__":
    main()

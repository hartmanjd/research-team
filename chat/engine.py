"""Answer a question about the visa employer data with Claude, citing the records it looked up.

The model only sees what the tools in chat/tools.py return. It cites records with markers such as
[employer 61603], [WHD case 1760819] and [application I-200-25126-941960]; `answer` turns each into a
link to the website and flags any marker whose ID never came back from a tool.
"""
import json, os, re

from .tools import TOOLS, run_tool

MODEL = os.environ.get("CHAT_MODEL", "claude-haiku-5-5")
SITE_URL = os.environ.get("SITE_URL", "https://visa-employer-watch.onrender.com").rstrip("/")
MAX_TOOL_ROUNDS = 8
MAX_TOKENS = 8000
# US dollars per million tokens (Haiku 5.5 for prompts up to 100K tokens). Cache writes cost 1.25x
# and cache reads 0.1x the input price.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}

SYSTEM = """You answer questions about U.S. employers that filed H-1B or H-2B visa applications in fiscal year 2025, and the Department of Labor Wage and Hour Division (WHD) enforcement cases linked to them. People using you include investigators deciding which employers to look at.

Use only what the tools return. Do not use outside knowledge about any company, and do not guess. If the tools cannot answer the question, say that the data doesn't cover it and, when useful, what it does cover.

Cite every employer, WHD case and application you mention, right after the fact, with these exact markers:
- [employer 61603] using the employer_id
- [WHD case 1760819] using the WHD case_id
- [application I-200-25126-941960] using the DOL case_number
Only cite IDs that a tool returned in this conversation.

What the data means:
- Applications are FY2025 DOL disclosure records (LCA for H-1B, H-2B certifications), one row per case number, latest status.
- An employer row is one company name at one address in one program; one company can have several rows. Rows sharing a tax ID are listed under same_tax_id_elsewhere.
- WHD cases cover every law WHD enforces (minimum wage, overtime, child labor, H-1B, H-2B, H-2A and others) and every year in the data, not only visa violations. Say "visa-program violations" only for h1b_violations on an H-1B employer or h2b_violations on an H-2B employer.
- WHD records have no tax ID, so cases are linked to employers by cleaned name plus ZIP code or state. Some links are wrong (about 3 to 4 percent in a tax-ID test). When a single case drives your answer, mention that it is a name match.
- A case with 0 violations and $0 back wages means WHD investigated and recorded no violations.
- willful_violator is the employer's own Yes/No answer on its applications, not a DOL finding. It counts only when most applications say Yes; willful_yes gives the count.
- Money is in U.S. dollars. back_wages is the back wages WHD found owed; penalties are civil money penalties assessed.

Write for a non-specialist: lead with the answer, keep it short, use a small table for lists of more than three rows, and give numbers as the tools return them (round only for readability, and say so)."""

_MARKER = re.compile(r"\[(employer|WHD case|application) ([A-Za-z0-9-]+)\]")


def _seen_ids(result, seen):
    """Collect every employer_id, WHD case_id and case_number in a tool result, and which employer each
    WHD case was returned under."""
    if isinstance(result, list):
        for x in result:
            _seen_ids(x, seen)
    elif isinstance(result, dict):
        if result.get("employer_id") is not None:
            seen["employer"].add(str(result["employer_id"]))
        if result.get("case_number"):
            seen["application"].add(str(result["case_number"]).upper())
        for x in result.values():
            _seen_ids(x, seen)
        employer, cases = result.get("employer"), result.get("cases")
        if isinstance(cases, list):  # get_employer's linked cases ("cases" elsewhere is a count)
            for c in cases:
                seen["WHD case"].add(str(c["case_id"]))
                if isinstance(employer, dict) and employer.get("employer_id") is not None:
                    seen["case_employer"][str(c["case_id"])] = employer["employer_id"]


def link_citations(text, seen):
    """Turn citation markers into Markdown links; return the text, the citations and the unverified ones."""
    citations, unverified = [], []

    def sub(m):
        kind, ident = m.group(1), m.group(2)
        key = ident.upper() if kind == "application" else ident
        ok = key in seen[kind]
        url = None
        if ok and kind == "employer":
            url = f"{SITE_URL}/#/employer/{key}"
        elif ok and kind == "application":
            url = f"{SITE_URL}/#/application/{key}"
        elif ok and key in seen["case_employer"]:
            url = f"{SITE_URL}/#/employer/{seen['case_employer'][key]}"
        c = {"kind": kind, "id": key, "url": url, "verified": ok}
        if c not in citations:
            citations.append(c)
        if not ok:
            unverified.append(c)
            return f"{m.group(0)} (unverified)"
        return f"[{kind} {key}]({url})" if url else m.group(0)

    return _MARKER.sub(sub, text), citations, unverified


def cost_usd(model, usage):
    p_in, p_out = PRICES.get(model, (0, 0))
    return (usage["input_tokens"] * p_in + usage["cache_creation_input_tokens"] * p_in * 1.25
            + usage["cache_read_input_tokens"] * p_in * 0.1 + usage["output_tokens"] * p_out) / 1e6


def answer(con, question, history=(), client=None, model=MODEL, effort=None):
    """Answer `question`, with earlier turns in `history` as [{"role", "content"}] text messages.

    Returns the linked answer, the raw text, citations, unverified citations, the tool calls made
    (name, input, error), token usage, estimated cost and the stop reason.
    """
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    messages = [dict(m) for m in history] + [{"role": "user", "content": question}]
    seen = {"employer": set(), "WHD case": set(), "application": set(), "case_employer": {}}
    calls = []
    usage = dict(input_tokens=0, output_tokens=0, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    extra = {"output_config": {"effort": effort}} if effort else {}
    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = client.messages.create(model=model, max_tokens=MAX_TOKENS, system=SYSTEM, tools=TOOLS,
                                          messages=messages, cache_control={"type": "ephemeral"}, **extra)
        for k in usage:
            usage[k] += getattr(response.usage, k, 0) or 0
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            call = {"name": block.name, "input": block.input}
            try:
                out = run_tool(con, block.name, block.input)
            except (KeyError, LookupError, ValueError, TypeError) as e:
                call["error"] = str(e.args[0]) if e.args else repr(e)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": f"Error: {call['error']}",
                                "is_error": True})
            else:
                _seen_ids(out, seen)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)})
            calls.append(call)
        messages.append({"role": "user", "content": results})
    raw = "".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "tool_use":
        raw = (raw + "\n\n" if raw else "") + "I needed more lookups than allowed for one question. Try a narrower question."
    elif response.stop_reason == "refusal":
        raw = "I can't answer that one. Try asking about employers, applications or WHD cases in the data."
    elif response.stop_reason == "max_tokens":
        raw += "\n\n(The answer was cut off because it ran too long.)"
    text, citations, unverified = link_citations(raw, seen)
    return {"answer": text, "raw": raw, "citations": citations, "unverified": unverified, "tool_calls": calls,
            "usage": usage, "cost_usd": cost_usd(model, usage), "model": model, "stop_reason": response.stop_reason}

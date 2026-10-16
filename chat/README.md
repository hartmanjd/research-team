# Chat engine

Answers plain-English questions about the visa employer data with Claude, using only the database.
The model calls the lookups in `tools.py` (thin wrappers over `dashboard/queries.py`, the same queries
the website uses) and cites every employer, WHD case and application it mentions. `engine.py` turns the
citations into links to the website and flags any citation whose ID no lookup returned.

The default model is Claude Haiku 5.5 (`claude-haiku-5-5`, $0.10 per million input tokens and $0.50 per
million output tokens for prompts up to 100K tokens). Set `CHAT_MODEL` to use another.

## Try it

You need an Anthropic API key:

1. Sign in at https://platform.claude.com, open **API keys**, and create a key. Copy it; it is shown once.
2. While you are there, set a monthly spend limit under **Billing** (for example $10) as a safety net.
3. In the terminal, with the virtual environment active (see `web/README.md`):

        pip install -r requirements.txt
        export ANTHROPIC_API_KEY=sk-ant-...      # paste your key; this lasts until the terminal closes
        python3 -m chat "Which H-2B employers in Texas had the most back wages?"

   The answer prints with the lookups it made, the tokens used and the cost. Add `--json` to see
   everything, including each citation and whether it was verified.

Never put the key in a file in this repo.

## Check the answers

`eval.py` writes about 40 questions from the current database, with the expected numbers and the
records that should be cited, asks the chat each one and grades the answers:

    python3 -m chat.eval --list          # the questions and expected answers, no API calls
    python3 -m chat.eval --out chat-eval.json

Each case passes when every expected number appears (allowing for rounding), the expected records are
cited, and no citation points at an ID the lookups never returned. Four questions ask for things the data
does not hold (company revenue, future investigations, older years); those pass when the answer says
so. The summary gives the pass count and the total and per-question cost. `--only visa` runs one kind,
`--model claude-sonnet-5-5` compares another model.

## Files

| File | What it is |
| --- | --- |
| tools.py | The eight lookups the model can call, their descriptions and input schemas |
| engine.py | The instructions, the question-and-lookup loop, citation links and checks, and cost |
| __main__.py | `python3 -m chat`: ask one question from the terminal |
| eval.py | The question set built from the database, the grader and the eval runner |
| tests/test_chat.py | Tests with a scripted stand-in for the model, so they make no API calls |

Run the tests from the repo root with `python3 -m unittest discover chat/tests`.

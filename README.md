# Document evaluation CLI

## Three-choice examples

`choose.py` provides two small classifiers using the same TypeSafe key and HTTP
client as the document evaluator:

| Example | Three choices |
| --- | --- |
| `feedback` | Bug report, Feature request, Praise |
| `game` | Attack, Defend, Heal |

Try either without a key (prints the request, not a simulated prediction):

```bash
python3 choose.py feedback --sample 1 --dry-run
python3 choose.py game --sample 3 --dry-run
```

Enter your own input and TypeSafe key:

```bash
python3 choose.py feedback --text "The app crashes when I export a PDF" --prompt-key
python3 choose.py game --text "I have 10/100 HP and 2 potions. The enemy is stunned this turn." --prompt-key
```

Omit `--text` to enter one line interactively, or pipe one line into stdin.
Use `--list-samples` to see the three built-in inputs, `--sample 1` (or 2/3) to
select one, and `--json` for machine-readable results. If `TYPESAFE_API_KEY` is
already set, omit `--prompt-key`. OpenRouter credentials remain separate.

The output shows the selected option, all three probabilities, and confidence.
A separate Noul question checks whether the input fits the example; both questions
run in the same request. Confidence below `--review-below-confidence` (default 0.5)
or applicability below 0.8 marks the choice provisional and prints a review reason.
These are illustrative thresholds, not validated accuracy guarantees. A successful
request exits 0 even when review is needed; inspect `needs_review` in JSON. Errors
exit 2. Neither example executes actions or changes a game state.

Feedback uses one primary category: a concrete bug takes precedence over a feature
request, then praise. Unrelated text or unsupported complaint types are flagged by
the applicability check. This is single-label sorting, not sentiment analysis.

The game example is a turn-based battle advisor: Attack damages the enemy, Defend
reduces the next hit, and Heal consumes a potion and a turn. Describe player health,
potion availability, and what the enemy is doing. The model recommends an action;
it does not simulate combat or deterministically enforce game rules. Edit the
instructions, options, and sample inputs in [feedback.json](examples/feedback.json)
or [game.json](examples/game.json) to experiment.

## Document scoring

Evaluate UTF-8 text and Markdown documents on configurable dimensions using
TypeSafe's Jev API. Requires Python 3.10+; no packages need installing.

Try the sample without an API key or network access:

```bash
python3 evaluate.py examples/document.md --rubric examples/rubric.json --dry-run
```

For a real evaluation, enter your own **TypeSafe** key at the hidden prompt:

```bash
python3 evaluate.py examples/document.md --rubric examples/rubric.json --prompt-key
```

Get that key from https://console.typesafe.ai/keys. The prompt never saves it.
For repeated runs, set `TYPESAFE_API_KEY` in your shell. `.env` files are ignored
by Git but are not automatically loaded by this CLI. Do not put keys in rubrics.

Your Pi assistant can keep using OpenRouter. Pi's OpenRouter credentials and this
application's TypeSafe credentials are separate: an OpenRouter key cannot replace
`TYPESAFE_API_KEY`. This CLI runs as a normal shell command from Pi and does not
read or change Pi's settings. No OpenRouter calls or generated explanations are
included in this initial version.

Evaluate multiple files or a directory recursively:

```bash
python3 evaluate.py ./my-documents --rubric examples/rubric.json --prompt-key --output report.json
python3 evaluate.py first.md second.txt --rubric examples/rubric.json --format csv --output report.csv
```

Output files must be new and their parent directory must already exist. Progress
goes to stderr; JSON or CSV goes to stdout unless `--output` is set. Exit codes:
0 = success, 1 = one or more API evaluations failed (successful results retained),
2 = configuration/input error. `--dry-run` always emits JSON request bodies,
including document text, and never sends requests.

## Define your dimensions

Copy `examples/rubric.json`. Its clarity/actionability dimensions for project
updates are illustrative, pending your actual document types and evaluation needs.

Each dimension has a complete `instructions` question, 2–10 concrete `levels`
ordered worst to best, and a nonnegative `weight` (default 1). At least one weight
must be positive. All dimensions in this version use the Score primitive.
Use `context` for audience, requirements, or reference facts. Questions can refer
to `document.text` and `context`. TypeSafe does not see question IDs as instructions.

The CLI sends one request per document containing every dimension. It normalizes
each returned score with `100 * score / (number_of_levels - 1)` and calculates the
weighted mean. JSON preserves probabilities, confidence, usage, the resolved model,
the rubric, and a document hash. CSV contains one row per document/dimension.

Confidence values below `review_below_confidence` flag that dimension for review; any flagged
dimension flags its document, even if its weight is zero. The example 0.5 threshold
needs validation on your data. Confidence describes the distribution, not a
guarantee of truth. A composite score is not an appropriate override for mandatory
pass/fail requirements. Jev returns structured judgments, not prose explanations.

## Limits and verification

Only `.txt`, `.md`, and `.markdown` are supported. PDF/DOCX/OCR extraction is not
included. Inputs are validated before sending any requests; documents are never
silently truncated. A conservative 28,000-byte request limit helps stay under
Jev's context budget without a tokenizer; split larger documents explicitly.

Requests time out after 60 seconds per attempt. Selected transient HTTP failures
retry up to twice with backoff; numeric Retry-After values up to 60 seconds are
honored. Longer delays return an error. Connection failures are not auto-retried.
Live evaluations transmit document content and rubric context to TypeSafe.

```bash
python3 -m unittest discover -s tests -v
```

Tests mock the API; no live evaluation has been performed without your key.
Official API and architecture references are cached in [docs](docs/README.md).

## Python formatting and linting

Ruff formats Python with four-space indentation and an 88-character target line
length, and checks imports, unused names, syntax/style errors, and common bug
patterns. Configuration lives in `pyproject.toml`; cached upstream docs are excluded.
See the [official Ruff configuration reference](https://docs.astral.sh/ruff/configuration/).
The runtime CLIs still need no third-party packages.

Install the pinned development tool:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Format and fix automatically fixable lint issues:

```bash
.venv/bin/ruff check --fix .
.venv/bin/ruff format .
```

Check formatting, lint, and tests without modifying files:

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
python3 -m unittest discover -s tests -v
```

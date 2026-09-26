# Jev examples: classify, choose, review, and score

Four small Python examples using TypeSafe's Jev API. Requires **Python 3.10+**;
the examples use the standard library, so no runtime packages need installing.

| Example | What it does | TypeSafe primitives |
| --- | --- | --- |
| [Comment review](#comment-review) | Reviews changed Python comments: Keep, Shorten, or Remove | Choice + Noul |
| [Feedback sorting](#three-choice-examples) | Sorts feedback: Bug report, Feature request, or Praise | Choice + Noul |
| [Game action chooser](#three-choice-examples) | Recommends Attack, Defend, or Heal from a battle situation | Choice + Noul |
| [Document scoring](#document-scoring) | Scores documents on configurable, weighted dimensions | Score |

**Choice** selects an option and returns probabilities and confidence. **Noul**
returns a 0–1 probability of yes; these examples use it to check input relevance
or sufficient context. **Score** rates content against ordered descriptions.
Jev supplies decisions; application code or a coding LLM performs any later action.

## Interactive guide — Jev in a harness

For learning the API and the harness economics, open the interactive guide in
[`ui/`](ui/README.md). It is a static page (no build step, no packages) with five
sections: why context growth is the cost problem, a request playground with
offline simulation, a cost lab for the four levers (prune, route, replace,
verify), integration patterns, and an API reference.

```bash
export TYPESAFE_API_KEY=ts_...
python3 ui/serve.py
# open http://127.0.0.1:8765/
```

The bundled `serve.py` serves the page and proxies the API from the server side.
That proxy is required for live calls: `api.typesafe.ai` sends no
`Access-Control-Allow-Origin` for third-party origins, so a browser cannot call it
directly from a static host. The key stays in the server environment and is never
sent to the browser.

The cost lab's arithmetic is exact and shown on the page; its keep rate, routing
split, and replace rate are assumptions you set. Jev's price ($0.042 per 1M input
tokens, output free) is the published rate.

## Quick start — no key needed

Run these from the repository root:

```bash
python3 review_comments.py --demo --dry-run
python3 choose.py feedback --sample 1 --dry-run
python3 choose.py game --sample 3 --dry-run
python3 evaluate.py examples/document.md --rubric examples/rubric.json --dry-run
```

Dry runs print the exact request, including source/input text. They make no API
calls and do not produce simulated predictions. Replace `--dry-run` with
`--prompt-key` to try a live evaluation with a hidden key prompt.

## Keys and Pi / OpenRouter

Get a **TypeSafe API key** from https://console.typesafe.ai/keys. The key prompt
never saves it. For repeated runs, export `TYPESAFE_API_KEY` in your shell and
omit `--prompt-key`. `.env` files are ignored by Git but are not automatically
loaded. Do not put keys in example files or rubrics.

Your Pi assistant can keep using OpenRouter. An OpenRouter key cannot replace the
TypeSafe key. These examples run as ordinary shell commands, do not change Pi's
settings, and do not call OpenRouter or generate replacement prose/code.

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

## Comment review

Review added or changed Python comments in a Git diff. Jev chooses **Keep,
Shorten, or Remove**, while a Noul checks whether the supplied code provides
enough context. The bundled demo contains obvious narration, a useful constraint,
and a repetitive explanation.

```bash
python3 review_comments.py --demo --dry-run
python3 review_comments.py --demo --prompt-key
python3 review_comments.py --repo . --prompt-key --json
python3 review_comments.py --repo . --staged --prompt-key --json
python3 review_comments.py --repo . --base HEAD~1 --prompt-key --json
```

Default scope is working-tree changes against HEAD, including untracked,
nonignored Python files. `--staged` reads the index; `--base <commit>` reviews
changes since a chosen commit. A clean repository has no comments to review, so
use `--demo` to try it immediately.

The reviewer extracts actual `#` comments, groups adjacent comment lines, includes
nearby code, and skips common directives, legal notices, and tracking comments.
It does not review docstrings or JavaScript/TypeScript yet. Uncertain decisions
are marked for review. JSON includes probabilities, confidence, model, source
hashes, skipped comments, and errors. Edit the [comment policy](examples/comment_policy.json)
to experiment with your team's conventions.

**This example never edits files or installs an agent hook.** For a real workflow:

```text
Coding LLM finishes task → lint/tests → review Git diff with Jev
    → send suggestions back to LLM → verify edits → finish
```

Jev selects the action; the coding LLM writes shortened comments or refactored code.
A future guarded script could perform simple deletions. The
[production design document](docs/comment-review-design.md) explains task baselines,
hook integration, ESLint adapters, caching, stale-result protection, and bounded
repair loops.

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

### Define your dimensions

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

### Document input limits

Only `.txt`, `.md`, and `.markdown` are supported. PDF/DOCX/OCR extraction is not
included. Inputs are validated before sending any requests; documents are never
silently truncated. A conservative 28,000-byte request limit helps stay under
Jev's context budget without a tokenizer; split larger documents explicitly.

## Shared API behavior and verification

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

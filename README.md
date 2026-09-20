# Document evaluation CLI

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

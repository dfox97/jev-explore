# Jev comment review: example and production plan

## Responsibilities

Jev evaluates supplied state and returns typed judgments. It does not itself edit
files, invoke tools, execute shell commands, or generate replacement prose. It is
broader than a classifier: Choice selects an option, Score rates a dimension, and
Noul estimates whether a proposition is true. Application code can map its output
to actions; the TypeSafe function-calling cookbook demonstrates this separation.

| Decision | Current example | Possible future executor |
| --- | --- | --- |
| Keep | Report keep | No edit |
| Shorten | Report shorten | Coding LLM writes a minimal replacement |
| Remove | Report remove | Coding LLM edits, or a guarded token-range deletion |
| Uncertain / context missing | Report review | Preserve comment and request more context |

A model's decision to remove is not permission to delete. Even simple deletion
requires a source-version check and exclusions for machine-significant comments.
Arbitrary refactoring requires a coding LLM and normal tests; Jev can evaluate a
proposed change but cannot generate the refactored program.

## Run the working example

```bash
python3 review_comments.py --demo --dry-run
python3 review_comments.py --demo --prompt-key
python3 review_comments.py --repo . --dry-run
python3 review_comments.py --repo . --prompt-key --json
python3 review_comments.py --repo . --staged --prompt-key --json
python3 review_comments.py --repo . --base <task-start-commit> --json
```

`--demo` uses three illustrative comments: obvious narration, a useful constraint,
and a repetitive explanation. These are inputs, not recorded Jev predictions.
Set `TYPESAFE_API_KEY` to omit `--prompt-key`. OpenRouter remains the coding
assistant provider; this reviewer calls TypeSafe directly and uses no OpenRouter key.

Default scope is the working tree relative to HEAD, including staged changes and
untracked, nonignored Python files. `--staged` reads the actual index contents and
excludes untracked files. `--base` permits reviewing work across multiple commits.
Deleted files/comments are not evaluated. Paths are obtained through NUL-delimited
Git output, then old/new text is compared with difflib, avoiding patch-header parsing.

Python's tokenizer extracts actual `#` comments, so strings containing `#` are not
mistaken for comments. Consecutive standalone comments at the same indentation are
reviewed as a block if any line changed. Inline comments on changed code lines can
be included even if the comment text itself is unchanged. Surrounding context uses
12 lines on each side and the full innermost containing function/class where present.
Comments above a definition currently receive the nearby line window.

Shebangs, encoding declarations, common tool directives, legal notices, and
TODO/FIXME/HACK/XXX tracking comments are skipped conservatively. This list is
illustrative and must be extended for a real repository. Docstrings are not reviewed.
Symlinks are skipped. Syntax errors and oversize files/requests are reported rather
than silently treated as successful reviews. The existing 1 MB file and 28,000-byte
request limits apply. Large context is not silently truncated.

Each candidate makes one request containing:

- Choice: `keep`, `shorten`, or `remove`.
- Noul: whether supplied context is sufficient to assess the comment.

The Noul cannot see the Choice answer. Neither question evaluates code correctness.
Confidence below 0.8 (configurable) or context probability below 0.8 flags review.
These are starting thresholds, not calibrated guarantees. JSON preserves the raw
choice, probabilities, model, usage, source hash, and request hash. Human-readable
messages are deterministic templates, not Jev-generated reasoning.

Exit 0 means processing completed, including advisory suggestions; it is not a
claim that comments are correct. Exit 1 means some file/request reviews failed;
successful results remain in the report. Exit 2 means a setup/input failure.
No candidates means no key or API request is needed. Dry runs print source context.
Real evaluations transmit that context to TypeSafe. No file edits, automatic cache,
hook installation, or OpenRouter rewrite requests are implemented in this example.

## Recommended agent integration

Run the semantic review after the coding agent finishes a coherent task and after
formatting/linting. This provides stable code context and avoids judging temporary
comments halfway through an edit. Do not assume every assistant chat turn represents
a completed task. Use the particular agent runner's documented task-completion or
pre-finalization event; exact Pi event wiring remains a follow-up integration task.

```text
Task starts → record baseline and existing user edits
    ↓
Coding LLM completes changes → formatter, linter, tests
    ↓
Collect task-owned changed comments and relevant code
    ↓
Jev: keep / shorten / remove + context sufficiency
    ↓
Preserve uncertain cases; send actionable diagnostics to coding LLM
    ↓
LLM makes bounded comment-only edits → verify diff, lint, tests
    ↓
One recheck → report remaining findings → finish task
```

Git diff does not identify authorship: capture pre-existing dirty changes or use an
isolated worktree at task start. HEAD alone misses changes after the agent commits;
retain the start revision. The example reviews the requested diff regardless of author.

Suppress hook re-entry while reviewing/fixing, cap repair attempts, and never hide
API failures behind a success status. Feedback should be structured as path, span,
original comment, suggested action, probabilities, and source hash. Start advisory;
do not block task completion on subjective findings until performance is measured.

## Plan for a real project

1. **Label representative comments.** Include useful long explanations, short
   redundant notes, public API documentation, directives, generated files, external
   workarounds, mixed blocks, and comments containing instruction-like text. Measure
   precision of removal suggestions, agreement with maintainers, latency, and cost.
   Confidence alone does not establish correctness.
2. **Add language adapters.** Retain Python tokenize/AST support. For JS/TS, use the
   configured parser to extract comments and enclosing syntax. Keep network calls in
   an async review script; optionally expose completed diagnostics through an ESLint
   rule. Add appropriate handling for JSDoc, docstrings, directives, and licenses.
3. **Improve scope and context.** Track agent-owned changes, add include/exclude
   paths, handle generated/vendor files, collect relevant imports and contracts, and
   explicitly assess comments whose associated code changed even if their text did
   not. Add rename-aware tracking and tests for unusual filenames and merge conflicts.
4. **Add reproducible caching and budgets.** Cache by comment, relevant source,
   policy, model version, and question definitions. Invalidate after edits. Pin a
   model version for evaluations, limit candidates per task, and benchmark batching
   multiple comments per file against the current isolated requests.
5. **Integrate the task hook.** Implement and test the selected runner's lifecycle
   event, snapshot collection, structured feedback, cancellation, timeout handling,
   and re-entry protection. Keep the TypeSafe key separate from OpenRouter credentials.
6. **Optionally add an executor.** Prefer passing shorten/remove suggestions to the
   existing coding agent. Require the original source hash to match before editing.
   A deterministic remover must operate on verified token spans, preserve newlines
   and directives, and reject mixed-purpose blocks. Validate that the diff changes
   only intended comments and that the AST is unchanged; still run project checks.
   Never apply stale suggestions to shifted line numbers.

## References

TypeSafe references were fetched on 2026-09-20 and are cached locally:

- [Primitives](typesafe/primitives.md): https://docs.typesafe.ai/primitives
- [Choice](typesafe/primitives-choice.md): https://docs.typesafe.ai/primitives/choice
- [Noul](typesafe/primitives-noul.md): https://docs.typesafe.ai/primitives/noul
- [State](typesafe/concepts-state.md): https://docs.typesafe.ai/concepts/state
- [Function calling](typesafe/cookbooks-function_calling.md): https://docs.typesafe.ai/cookbooks/function_calling
- ESLint rule/comment APIs: https://eslint.org/docs/latest/extend/custom-rules

The workflow and thresholds above are this project's proposed design, not a claim
that TypeSafe or Pi supplies an automatic comment-editing integration.

# Local documentation reference

Fetched from the official TypeSafe documentation on **2026-09-20**. These are
local snapshots, not a guarantee of current limits or model versions. Consult
these files first; refresh relevant pages when API behavior changes. Markdown
snapshots preserve upstream MDX components, which may not render outside Mintlify.

| Local file | Official source |
| --- | --- |
| [Index](typesafe/llms.txt) | https://docs.typesafe.ai/llms.txt |
| [Introduction](typesafe/introduction.md) | https://docs.typesafe.ai/introduction.md |
| [Quick start / API keys](typesafe/introduction-quickstart.md) | https://docs.typesafe.ai/introduction/quickstart.md |
| [HTTP API](typesafe/api.md) | https://docs.typesafe.ai/api.md |
| [Score](typesafe/primitives-score.md) | https://docs.typesafe.ai/primitives/score.md |
| [State](typesafe/concepts-state.md) | https://docs.typesafe.ai/concepts/state.md |
| [Building guide](typesafe/concepts-how-to-build-with-system-one.md) | https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md |
| [Composite scoring](typesafe/patterns-composite-scoring.md) | https://docs.typesafe.ai/patterns/composite-scoring.md |
| [Parallel questions cookbook](typesafe/cookbooks-parallel_questions.md) | https://docs.typesafe.ai/cookbooks/parallel_questions.md |
| [Confidence](typesafe/confidence.md) | https://docs.typesafe.ai/confidence.md |
| [Models and limits](typesafe/models.md) | https://docs.typesafe.ai/models.md |

The implementation uses the HTTP API directly, with Python's standard library.
The existing [.pi TypeSafe skill](../.pi/skills/typesafe-ai/SKILL.md) guided the
architecture: independent questions in one request per document, explicit rubrics,
and deterministic weighting in code. No SDK installation or OpenAI account is needed.

Pi/OpenRouter is the development assistant setup. The TypeSafe quick start
documents a separately issued TypeSafe key and TypeSafe endpoint. This integration
does not route Jev requests through OpenRouter or read Pi credentials.

Refresh an individual reference explicitly, for example:

```bash
curl -fsSL https://docs.typesafe.ai/api.md -o docs/typesafe/api.md
```

Record a new fetch date when refreshing. Prefer the local references during routine
development and recheck live docs for authentication, contract, model, or limit changes.

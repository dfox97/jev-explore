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
| [Primitives overview](typesafe/primitives.md) | https://docs.typesafe.ai/primitives.md |
| [Score](typesafe/primitives-score.md) | https://docs.typesafe.ai/primitives/score.md |
| [Choice](typesafe/primitives-choice.md) | https://docs.typesafe.ai/primitives/choice.md |
| [Noul / applicability check](typesafe/primitives-noul.md) | https://docs.typesafe.ai/primitives/noul.md |
| [Function calling cookbook](typesafe/cookbooks-function_calling.md) | https://docs.typesafe.ai/cookbooks/function_calling.md |
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

`choose.py` uses Choice for one of three feedback categories or game actions, with
an independent Noul to check whether the input fits the scenario. Questions do not
see each other's answers: the applicability check defines scope directly, and code
combines the responses afterward. The three additional references above were fetched
on 2026-09-20. A review flag is application behavior, not a fourth Choice option.

## Where this project uses Noul

Verified against the official primitives overview on 2026-09-20; the overview is
now saved as `typesafe/primitives.md`. The detailed Noul reference was already
cached as `typesafe/primitives-noul.md`.

| CLI | Primitives | Noul question |
| --- | --- | --- |
| `choose.py feedback` | Choice + Noul | Does the input contain product feedback matching a bug report, feature request, or praise? |
| `choose.py game` | Choice + Noul | Does the input describe an ongoing battle with enough health, potion, and enemy-action information to choose an action? |
| `evaluate.py` | Score | None; each configured dimension is a Score. |

`choose.py` sends a `decision` Choice and an `applicable` Noul together. The Noul
returns the probability of yes, from 0 to 1, with no separate confidence field.
The CLI displays it as "Input fits example" and exposes it in JSON as
`applicable_probability`. Values below 0.8 mark the choice provisional and set
`needs_review`; this threshold is an example policy, not a TypeSafe requirement.
A value near 0.5 means uncertainty about yes versus no, not moderate intensity.

Pi/OpenRouter is the development assistant setup. The TypeSafe quick start
documents a separately issued TypeSafe key and TypeSafe endpoint. This integration
does not route Jev requests through OpenRouter or read Pi credentials.

Refresh an individual reference explicitly, for example:

```bash
curl -fsSL https://docs.typesafe.ai/api.md -o docs/typesafe/api.md
```

Record a new fetch date when refreshing. Prefer the local references during routine
development and recheck live docs for authentication, contract, model, or limit changes.

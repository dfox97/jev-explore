# Jev interactive guide (`ui/`)

A static, dependency-free single-page guide to using the TypeSafe Jev API in an
agent harness. No build step: `index.html` + `styles.css` + `app.js`.

Sections: **Why** (the context-growth problem), **Playground** (build a real
request, simulate or send it), **Cost lab** (prune / route / replace / verify,
with the arithmetic exposed), **Patterns** (when code, Jev, or an LLM), and
**Reference** (contract, limits, errors, key setup).

## Two ways to open it

**Static** — the published copy. Everything works except live API calls, because
`api.typesafe.ai` does not send `Access-Control-Allow-Origin` for third-party
origins and the browser blocks the response.

**Local, with live calls** — the bundled standard-library server serves the page
and proxies `/api/evaluate` to TypeSafe from the server side:

```bash
export TYPESAFE_API_KEY=ts_...
python3 ui/serve.py
# open http://127.0.0.1:8765/
```

The page probes `GET /api/health` on load. When the proxy is present it enables
**Send live** and hides the key field, because the key stays in the server
environment and is never sent to the browser. If no environment key is set, the
page offers a local-only key field so you can still try a call.

The proxy accepts only `POST /api/evaluate` with a JSON body containing
`{ "payload": <systemone request> }`. It never forwards an arbitrary URL and
never echoes the key.

## Cost lab honesty

The arithmetic is exact and shown in the "arithmetic" panel. The **keep rate**,
**routing split**, **replace rate**, prices and token sizes are assumptions you
set. Jev's price is the published rate ($0.042 per 1M input tokens, output free)
and is fixed.

The **Simulate** button in the playground is a deterministic local stand-in so
the page is useful offline. It is labelled as such and is not a Jev prediction.

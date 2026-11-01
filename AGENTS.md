# Base44 sandbox notes

This repository is a Python SDK (`google.antigravity`), not a web app. The
sandbox setup in `docker-compose.base44.yml` is a development harness, not part
of the shipped package.

## Running it here

```sh
docker compose -f docker-compose.base44.yml up -d --build
```

- `demo/server.py` is a small ASGI console (page at `/`, SSE chat at
  `POST /api/chat`) that exercises `Agent` + `LocalAgentConfig`. It is sandbox
  tooling; keep SDK behavior changes out of it.
- The app boots healthy with no API key. Agent calls then fail with a clear
  error, and the page shows a banner.

## Non-obvious: the `localharness` binary

The SDK talks to a compiled Go binary (`google/antigravity/bin/localharness`)
that is **not in this repo** — it only ships inside the platform wheels on PyPI
(see README). `Dockerfile.base44` therefore installs a wheel, copies the binary
to `/usr/local/bin/localharness`, then uninstalls the wheel so the bind-mounted
source is what Python imports (`ANTIGRAVITY_HARNESS_PATH` points at the copy).

The wheel is pinned to **0.1.7**, which is the closest published release to this
source snapshot: it shares the `connections/local/localharness_pb2.py` layout and
its proto contains every field this source sends. Tested alternatives:

- `0.1.5` (pyproject's version): binary rejects the init event with
  `unknown field "readUrlContent"`.
- `0.1.23`: init handshake fails after the WebSocket opens.

If the source is updated, re-check the pin by running a single agent call; the
harness/proto mismatch surfaces immediately as an init-handshake error.

## Credentials

`GEMINI_API_KEY` (Gemini Developer API, https://aistudio.google.com/apikey) is
delivered by the platform to `/run/base44/app.env` and read by the harness
process. Vertex AI is an alternative but needs GCP Application Default
Credentials, which the sandbox does not have.

The default model is `gemini-3.5-flash` (`google/antigravity/models.py`).

## Verifying

```sh
# SDK unit tests (inside the container; the host has no Python)
docker compose -f docker-compose.base44.yml exec -T demo python -m pytest google/antigravity -q

# One real agent call through the console endpoint
curl -sN -X POST http://localhost:3000/api/chat \
  -H 'Content-Type: application/json' -d '{"prompt":"Say Hello World!"}'
```

Edits under `demo/` and `google/` hot-reload through uvicorn's watcher.

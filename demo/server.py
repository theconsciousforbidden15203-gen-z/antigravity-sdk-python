# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Browser console for the Google Antigravity SDK.

This is a small demo harness, not part of the SDK itself. It serves one page and
a streaming chat endpoint so the SDK can be exercised from a browser:

  GET  /           the console page
  POST /api/chat   {"prompt": "..."} -> server-sent events of agent text tokens

Run it with:
  uvicorn demo.server:app --host 0.0.0.0 --port 3000

The agent uses the default ``LocalAgentConfig`` (read-only tools, and
``run_command`` denied), so nothing on the page can mutate the machine.
"""

import json
import os

from google.antigravity import Agent
from google.antigravity import LocalAgentConfig

_SYSTEM_INSTRUCTIONS = (
    "You are a helpful assistant demonstrating the Google Antigravity SDK. Keep"
    " answers short and concrete, and format code in fenced blocks."
)

_SSE_HEADERS = [
    (b"content-type", b"text/event-stream"),
    (b"cache-control", b"no-cache"),
    (b"x-accel-buffering", b"no"),
]

_MISSING_KEY_BANNER = """
      <div class="banner">
        No <code>GEMINI_API_KEY</code> is configured, so agent calls will fail.
        Add it as a project secret and the console picks it up on restart.
      </div>
"""

_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Google Antigravity SDK</title>
    <style>
      :root {
        --bg: #0b0e14;
        --panel: #131822;
        --line: #232b3a;
        --text: #e6e9ef;
        --muted: #93a1b5;
        --accent: #8ab4f8;
        --ok: #6ee7b7;
        --warn: #fbbf24;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        background: radial-gradient(900px 500px at 15% -10%, #16223a 0%, var(--bg) 60%);
        color: var(--text);
        font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        padding: 40px 20px 64px;
      }
      main { width: 100%; max-width: 780px; margin: 0 auto; }
      header { margin-bottom: 22px; }
      .brand { display: flex; align-items: center; gap: 10px; }
      .dot {
        width: 10px; height: 10px; border-radius: 50%;
        background: var(--ok); box-shadow: 0 0 12px var(--ok);
      }
      h1 { font-size: 22px; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
      .sub { color: var(--muted); font-size: 13px; margin: 6px 0 0 20px; }
      .banner {
        border: 1px solid rgba(251, 191, 36, 0.35);
        background: rgba(251, 191, 36, 0.08);
        color: #fde68a;
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 13px;
        margin-bottom: 18px;
      }
      .banner code { color: #fef3c7; }
      .card {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 18px;
        margin-bottom: 18px;
      }
      label {
        display: block;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 10px;
      }
      textarea {
        width: 100%;
        min-height: 92px;
        resize: vertical;
        background: #0e131c;
        border: 1px solid var(--line);
        border-radius: 12px;
        color: var(--text);
        font: inherit;
        padding: 12px 14px;
      }
      textarea:focus { outline: 2px solid rgba(138, 180, 248, 0.45); border-color: transparent; }
      .row { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; }
      .hint { color: var(--muted); font-size: 12px; }
      button {
        border: 0;
        border-radius: 10px;
        background: var(--accent);
        color: #071022;
        font: inherit;
        font-weight: 600;
        padding: 10px 22px;
        cursor: pointer;
      }
      button:disabled { opacity: 0.55; cursor: progress; }
      .card-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
      h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 0; font-weight: 600; }
      #status { font-size: 12px; color: var(--muted); }
      pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        font: 14px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
        min-height: 96px;
      }
      footer { color: var(--muted); font-size: 12px; text-align: center; }
    </style>
  </head>
  <body>
    <main>
      <header>
        <div class="brand"><span class="dot"></span><h1>Google Antigravity SDK</h1></div>
        <p class="sub">localharness demo console &middot; gemini-3.5-flash &middot; running from source</p>
      </header>
      __BANNER__
      <section class="card">
        <label for="prompt">Prompt</label>
        <textarea id="prompt" spellcheck="false">Say 'Hello World!'</textarea>
        <div class="row">
          <span class="hint">Cmd / Ctrl + Enter to send</span>
          <button id="send" type="button">Send</button>
        </div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Response</h2><span id="status">idle</span></div>
        <pre id="answer">Awaiting a prompt&hellip;</pre>
      </section>
      <footer>Read-only agent &middot; shell commands are denied by policy</footer>
    </main>
    <script>
      const promptEl = document.getElementById('prompt');
      const answerEl = document.getElementById('answer');
      const statusEl = document.getElementById('status');
      const sendBtn = document.getElementById('send');
      let busy = false;

      async function sendPrompt() {
        const prompt = promptEl.value.trim();
        if (!prompt || busy) return;
        busy = true;
        sendBtn.disabled = true;
        statusEl.textContent = 'thinking';
        answerEl.textContent = '';
        try {
          const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt }),
          });
          if (!res.ok || !res.body) throw new Error('request failed (' + res.status + ')');
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          while (true) {
            const chunk = await reader.read();
            if (chunk.done) break;
            buffer += decoder.decode(chunk.value, { stream: true });
            let sep;
            while ((sep = buffer.indexOf('\\n\\n')) !== -1) {
              const frame = buffer.slice(0, sep).trim();
              buffer = buffer.slice(sep + 2);
              if (!frame.startsWith('data:')) continue;
              const event = JSON.parse(frame.slice(5).trim());
              if (event.type === 'token') {
                answerEl.textContent += event.text;
                statusEl.textContent = 'streaming';
              } else if (event.type === 'error') {
                answerEl.textContent += (answerEl.textContent ? '\\n\\n' : '') + 'Error: ' + event.message;
                statusEl.textContent = 'error';
              } else if (event.type === 'done') {
                statusEl.textContent = 'done';
              }
            }
          }
        } catch (err) {
          answerEl.textContent = 'Error: ' + err.message;
          statusEl.textContent = 'error';
        } finally {
          busy = false;
          sendBtn.disabled = false;
          if (statusEl.textContent === 'thinking') statusEl.textContent = 'done';
        }
      }

      sendBtn.addEventListener('click', sendPrompt);
      promptEl.addEventListener('keydown', (event) => {
        if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') sendPrompt();
      });
    </script>
  </body>
</html>
"""


def _has_credentials() -> bool:
  return bool(os.environ.get("GEMINI_API_KEY"))


async def _read_body(receive) -> bytes:
  body = b""
  while True:
    message = await receive()
    body += message.get("body", b"")
    if not message.get("more_body", False):
      return body


async def _send_event(send, event: dict) -> None:
  payload = f"data: {json.dumps(event)}\n\n".encode()
  await send({"type": "http.response.body", "body": payload, "more_body": True})


async def _serve_page(send) -> None:
  banner = "" if _has_credentials() else _MISSING_KEY_BANNER
  body = _PAGE.replace("__BANNER__", banner).encode()
  await send({
      "type": "http.response.start",
      "status": 200,
      "headers": [
          (b"content-type", b"text/html; charset=utf-8"),
          (b"content-length", str(len(body)).encode()),
      ],
  })
  await send({"type": "http.response.body", "body": body})


async def _serve_chat(send, body: bytes) -> None:
  try:
    prompt = str(json.loads(body or b"{}").get("prompt", "")).strip()
  except json.JSONDecodeError:
    prompt = ""

  await send({"type": "http.response.start", "status": 200, "headers": _SSE_HEADERS})

  if not prompt:
    await _send_event(send, {"type": "error", "message": "Enter a prompt first."})
  else:
    try:
      config = LocalAgentConfig(system_instructions=_SYSTEM_INSTRUCTIONS)
      async with Agent(config) as agent:
        response = await agent.chat(prompt)
        async for token in response:
          await _send_event(send, {"type": "token", "text": token})
    except Exception as exc:  # pylint: disable=broad-except
      await _send_event(send, {"type": "error", "message": str(exc)})

  await _send_event(send, {"type": "done"})
  await send({"type": "http.response.body", "body": b"", "more_body": False})


async def app(scope, receive, send) -> None:
  """ASGI entry point."""
  if scope["type"] == "lifespan":
    while True:
      message = await receive()
      if message["type"] == "lifespan.startup":
        await send({"type": "lifespan.startup.complete"})
      elif message["type"] == "lifespan.shutdown":
        await send({"type": "lifespan.shutdown.complete"})
        return
    return

  if scope["type"] != "http":
    return

  path = scope["path"].rstrip("/") or "/"
  if scope["method"] == "GET" and path == "/":
    await _serve_page(send)
    return
  if scope["method"] == "POST" and path == "/api/chat":
    await _serve_chat(send, await _read_body(receive))
    return

  await send({
      "type": "http.response.start",
      "status": 404,
      "headers": [(b"content-type", b"text/plain; charset=utf-8")],
  })
  await send({"type": "http.response.body", "body": b"Not found"})

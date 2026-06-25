# HOWTOTEST: Caseware Procurement Document MCP Server

## Prerequisites

- Pipeline must have run at least once (`task pipeline` or `task`)
- For `answer_question` tests: Ollama running with `llama3.2` pulled

---

## Method 1 — Smoke test (quick)

```bash
task test
```

Waits 5s then checks the server responds to `tools/list`.  
Pass: JSON with 4 tool definitions printed.  
Fail: blank output or timeout — check DB exists and no import errors.

---

## Method 2 — MCP Inspector (interactive GUI)

```bash
.venv/bin/mcp dev \
  src/caseware_documents_mcp/server/fast_mcp_server.py:mcp \
  --with-editable .
```

Opens `http://localhost:6274`. Click each tool, fill params, inspect responses.  
Best for exploratory testing — no JSON-RPC knowledge needed.

---

## Method 3 — `mcp run` over SSE (TCP, scriptable)

Starts the server on a TCP port so you can connect with any HTTP client.

```bash
# Start the server in the background
.venv/bin/mcp run \
  src/caseware_documents_mcp/server/mcp_server.py:server \
  --transport sse &
PID=$!
sleep 3

# List tools
curl -s -X POST http://localhost:8000/tools/list

kill $PID 2>/dev/null
```

> **Note**: SSE transport support depends on the MCP SDK version. If the above fails, use Method 4 (raw stdio) instead.

---

## Method 4 — Raw stdio (no extra tools)

Pipe JSON-RPC messages directly to `main.py`. The server reads from stdin and writes to stdout.

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' \
  | .venv/bin/python -m src.caseware_documents_mcp.main --skip-pipeline 2>/dev/null
```

For multi-step sessions, use a script:

```bash
.venv/bin/python -m src.caseware_documents_mcp.main --skip-pipeline 2>/dev/null <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_documents","arguments":{"query":"invoice"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"find_order_evidence","arguments":{"order_number":"10687"}}}
EOF
```

> **Note**: The server is single-shot per invocation for batch mode. Each `printf`/heredoc call starts a fresh instance. Use `mcp run` (Method 3) for persistent sessions.

---

## Method 5 — Claude Desktop (real-world use)

1. Follow `MCPHOWTO.md` to add the server to `claude_desktop_config.json`.
2. Restart Claude Desktop.
3. Look for the hammer icon, then ask questions like:
   - "Which invoices are missing a purchase order?"
   - "Find all documents related to order 10687"
   - "Summarize the contract terms"

---

## Method 6 — Python test script (automated)

```bash
.venv/bin/python -m pytest tests/ -v
```

Requires `pytest`. Install with:
```bash
.venv/bin/pip install pytest
```

The test script at `tests/test_mcp_server.py` spawns a server process, runs JSON-RPC requests against each tool, and asserts correct response structures.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `tools/list` returns empty | Pipeline not run — do `task pipeline` first |
| `answer_question` returns raw excerpts | Ollama not running or `llama3.2` not pulled |
| ImportError / ModuleNotFoundError | `.venv` not activated or `pip install -e .` not run |
| Timeout on `task test` | Server starts but waits forever — the test doesn't send `initialize` first; use Method 6 (pytest) instead |
| `tools/list` returns `Invalid request parameters` | Must send `initialize` + `notifications/initialized` first — see Method 6 for the correct protocol sequence |

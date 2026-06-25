import json
import select
import subprocess
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_MODULE = "caseware_documents_mcp.main"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def send_request(proc, request: dict, timeout: int = 60) -> dict:
    line = json.dumps(request) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()
    fd = proc.stdout.fileno()
    start = time.time()
    data = ""
    while time.time() - start < timeout:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            chunk = proc.stdout.readline()
            if chunk:
                data += chunk
                try:
                    return json.loads(data.strip())
                except json.JSONDecodeError:
                    continue
    pytest.fail(f"Timeout reading response for request id={request.get('id')}")


def send_notification(proc, notification: dict):
    line = json.dumps(notification) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()


@pytest.fixture(scope="module")
def server_proc():
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", SERVER_MODULE, "--skip-pipeline"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        text=True,
        bufsize=1,
    )
    resp = send_request(proc, {
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }, timeout=120)
    assert resp.get("id") == 0
    send_notification(proc, {
        "jsonrpc": "2.0", "method": "notifications/initialized",
    })
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_tools_list(server_proc):
    resp = send_request(server_proc, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/list",
    })
    assert "result" in resp, f"No result: {resp}"
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"search_documents", "get_related_documents", "find_order_evidence", "answer_question"}


def test_search_documents(server_proc):
    resp = send_request(server_proc, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "search_documents",
            "arguments": {"query": "invoice"},
        },
    })
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "Search results" in text


def test_search_documents_type_filter(server_proc):
    resp = send_request(server_proc, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {
            "name": "search_documents",
            "arguments": {"query": "order", "document_type": "purchase_order"},
        },
    })
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "purchase_order" in text


def test_find_order_evidence_known(server_proc):
    resp = send_request(server_proc, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {
            "name": "find_order_evidence",
            "arguments": {"order_number": "10687"},
        },
    })
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "Evidence chain for order: 10687" in text


def test_find_order_evidence_unknown(server_proc):
    resp = send_request(server_proc, {
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {
            "name": "find_order_evidence",
            "arguments": {"order_number": "99999"},
        },
    })
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "No documents found" in text


def test_get_related_documents_invalid_id(server_proc):
    resp = send_request(server_proc, {
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {
            "name": "get_related_documents",
            "arguments": {"document_id": 99999},
        },
    })
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "not found" in text.lower()


def test_get_related_documents_valid(server_proc):
    resp = send_request(server_proc, {
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {
            "name": "get_related_documents",
            "arguments": {"document_id": 1},
        },
    })
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert any(word in text for word in ["Related documents", "Document with ID", "No related"])

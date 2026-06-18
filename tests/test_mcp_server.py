#!/usr/bin/env python3
"""Quick smoke-test for the MCP server — verifies JSON-RPC protocol over stdio."""

import json
import os
import subprocess
import sys
import threading
import time

SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server.py")


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-u", SERVER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "OPENAI_API_KEY": "sk-test-key", "PYTHONIOENCODING": "utf-8"},
    )

    # Background thread to collect stdout
    stdout_lines: list[str] = []
    _stop = threading.Event()

    def _reader():
        while not _stop.is_set():
            line = proc.stdout.readline()
            if not line:
                break
            stdout_lines.append(line)

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    def send(method: str, params: dict | None = None, req_id: int = 1) -> dict | None:
        nonlocal stdout_lines
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        line = json.dumps(payload) + "\n"
        proc.stdin.write(line)
        proc.stdin.flush()

        # Wait for response
        deadline = time.time() + 8.0
        collected = len(stdout_lines)
        while time.time() < deadline:
            if len(stdout_lines) > collected:
                # New data arrived
                new_count = len(stdout_lines)
                for i in range(collected, new_count):
                    raw = stdout_lines[i].strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                        if obj.get("id") == req_id:
                            collected = new_count
                            return obj
                    except json.JSONDecodeError:
                        pass
                collected = new_count
            time.sleep(0.1)

        # Fallback: dump all lines
        print(f"  [no response for id={req_id}, dumping {len(stdout_lines)} lines]")
        for ln in stdout_lines[-10:]:
            print(f"  > {ln.strip()[:120]}")
        return None

    # --- Step 1: Initialize ---
    print("1. Sending initialize ...")
    init_resp = send(
        "initialize",
        {
            "protocolVersion": "0.1.0",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
        req_id=1,
    )
    if init_resp:
        print(f"   Server: {init_resp.get('result', {}).get('serverInfo', {}).get('name', '?')} v{init_resp.get('result', {}).get('serverInfo', {}).get('version', '?')}")
    else:
        print("   No initialize response")
        proc.terminate()
        return 1

    # --- Step 2: tools/list ---
    print("2. Listing tools ...")
    list_resp = send("tools/list", req_id=2)
    if list_resp:
        tools = list_resp.get("result", {}).get("tools", [])
        print(f"   Found {len(tools)} tools:")
        for t in tools:
            name = t.get("name", "?")
            desc = t.get("description", "")[:70].replace("\n", " ")
            print(f"     - {name}: {desc}...")
    else:
        print("   No tools/list response")
        proc.terminate()
        return 1

    # --- Step 3: tools/call with dry-run (no LLM needed) ---
    print("3. Calling generate_tests with non-existent SDK (expect error / fast fail) ...")
    call_resp = send(
        "tools/call",
        {
            "name": "generate_tests",
            "arguments": {
                "sdk_root": "/tmp/nonexistent_sdk_xyz",
                "model": "longcat",
                "output_root": "./output",
            },
        },
        req_id=3,
    )
    if call_resp:
        is_error = call_resp.get("result", {}).get("isError", False) or "error" in call_resp.get("result", {}).get("content", [{}])[0].get("text", "")
        print(f"   Response received (isError={is_error})")
        content = call_resp.get("result", {}).get("content", [])
        for c in content[:3]:
            text_preview = c.get("text", "")[:120]
            print(f"   Content: {text_preview}...")
    else:
        print("   No tools/call response (expected — SDK not found)")

    _stop.set()
    proc.terminate()
    proc.wait(timeout=5)
    print("\n=== MCP Server Test Complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

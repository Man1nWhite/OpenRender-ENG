# End-to-end test: boots bridge.py like start.bat would and exercises it over WebSocket.
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
PORT = 17799
ws_root = Path(tempfile.mkdtemp(prefix="zs_bridge_test_"))

cfg_path = HERE / "config.json"
backup = cfg_path.read_text(encoding="utf-8")
cfg_path.write_text(json.dumps({
    "workspaceFolder": str(ws_root),
    "mcpServers": {"workspace": {"command": "workspace_mcp.py", "args": []}},
}, indent=2), encoding="utf-8")

env = dict(os.environ, ZS_BRIDGE_PORT=str(PORT), ZS_WORKSPACE_ROOT=str(ws_root))
proc = subprocess.Popen([sys.executable, str(HERE / "bridge.py")],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", env=env,
                        cwd=str(HERE))

results = []


async def main():
    import websockets
    ws = None
    for _ in range(60):  # up to 30s for boot
        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{PORT}", max_size=16 * 1024 * 1024)
            break
        except Exception:
            await asyncio.sleep(0.5)
    if ws is None:
        results.append(("bridge reachable", False))
        return
    results.append(("bridge reachable", True))

    rid = 0
    async def rpc(payload, timeout=40):
        nonlocal rid
        rid += 1
        payload["id"] = rid
        await ws.send(json.dumps(payload))
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == rid:
                return msg
            # status snapshots etc. arrive unsolicited; ignore
        raise TimeoutError(payload.get("type"))

    # 1. connected snapshot - may arrive before the workspace server finishes
    # booting, so poll until the probe flips true (the real extension does the
    # same via the bridge's periodic status pushes).
    msg = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < 30:
        m = await rpc({"type": "studio_status"}, timeout=20)
        if m.get("studio") is True:
            msg = m
            break
        await asyncio.sleep(1)
    results.append(("connected snapshot studio=true", msg is not None and msg.get("studio_app") is True))
    print("  snapshot:", {k: v for k, v in (msg or {}).items() if k != "tools"})

    # 2. tools list
    msg = await rpc({"type": "list_tools"}, timeout=60)
    names = [t["name"] for t in msg.get("tools", [])]
    results.append(("12 workspace tools advertised", len(names) == 12))
    print("  tools:", names)

    # 3. real tool call: write then read back through the server
    msg = await rpc({"type": "call_tool", "name": "write_file",
                     "arguments": {"path": "hello.txt", "content": "hello from the agent\n"},
                     "timeout": 30000}, timeout=60)
    ok1 = msg.get("ok") and "Created" in msg.get("text", "")
    msg = await rpc({"type": "call_tool", "name": "read_file",
                     "arguments": {"path": "hello.txt"}, "timeout": 30000})
    ok2 = msg.get("ok") and "hello from the agent" in msg.get("text", "")
    results.append(("call_tool write+read roundtrip", ok1 and ok2))
    print("  read:", (msg.get("text") or "")[:80].replace("\n", " / "))

    # 4. run_command through the whole stack
    py = sys.executable.replace("\\", "/")
    msg = await rpc({"type": "call_tool", "name": "run_command",
                     "arguments": {"command": f'"{py}" -c "print(21*2)"', "timeout_seconds": 20},
                     "timeout": 60000})
    results.append(("run_command works", msg.get("ok") is True and "42" in msg.get("text", "")))

    # 5. error surfaces as ok:false
    msg = await rpc({"type": "call_tool", "name": "read_file",
                     "arguments": {"path": "../escape.txt"}, "timeout": 30000})
    results.append(("escape attempt -> error", msg.get("ok") is False))

    # 6. workspace status snapshot
    msg = await rpc({"type": "workspace_status"})
    results.append(("workspace_status reports current",
                    msg.get("ok") is True and msg.get("ws_current") == str(ws_root)))
    results.append(("workspace_status has history",
                    isinstance(msg.get("ws_history"), list) and len(msg["ws_history"]) >= 1))

    # 7. one-click switch to a second folder (the menu's core feature)
    ws_root2 = Path(tempfile.mkdtemp(prefix="zs_ws_second_"))
    (ws_root2 / "second.txt").write_text("we are in the second folder\n", encoding="utf-8")
    msg = await rpc({"type": "set_workspace", "path": str(ws_root2)}, timeout=40)
    results.append(("set_workspace switches", msg.get("ok") is True and msg.get("ws_current") == str(ws_root2)))
    results.append(("history remembers both folders",
                    sorted(os.path.normcase(p) for p in msg.get("ws_history", [])) ==
                    sorted(os.path.normcase(str(p)) for p in (ws_root, ws_root2))))
    # give the restarted server a beat, then read a file that ONLY exists there
    await asyncio.sleep(1.5)
    msg = await rpc({"type": "call_tool", "name": "read_file",
                     "arguments": {"path": "second.txt"}, "timeout": 30000})
    results.append(("tool runs inside the NEW folder",
                    msg.get("ok") is True and "second folder" in msg.get("text", "")))
    # old root must now be OUTSIDE the sandbox
    msg = await rpc({"type": "call_tool", "name": "read_file",
                     "arguments": {"path": "hello.txt"}, "timeout": 30000})
    results.append(("previous folder no longer readable", msg.get("ok") is False))

    # invalid target refused
    msg = await rpc({"type": "set_workspace", "path": "Z:/no/existe"})
    results.append(("invalid folder rejected", msg.get("ok") is False))

    await ws.close()


try:
    asyncio.run(main())
finally:
    proc.terminate()
    try:
        out = proc.communicate(timeout=8)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        out = proc.communicate()[0]
    cfg_path.write_text(backup, encoding="utf-8")

print()
print("--- bridge output (tail) ---")
print("\n".join(out.splitlines()[-14:]))
print()
fails = [n for n, ok in results if not ok]
for n, ok in results:
    print(f"[{'OK  ' if ok else 'FAIL'}] {n}")
sys.exit(1 if fails else 0)

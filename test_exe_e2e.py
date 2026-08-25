# E2E test for the PACKAGED OpenRender.exe.
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
EXE = HERE / "dist" / "OpenRender.exe"
PORT = 17801


def out(*a):
    print(*a, flush=True)


if not EXE.is_file():
    out(f"FATAL: {EXE} not found - run build.py first")
    sys.exit(1)

ws_root = Path(tempfile.mkdtemp(prefix="zs_exe_ws_"))
stage = Path(tempfile.mkdtemp(prefix="zs_exe_app_"))
app_dir = stage / "app"
app_dir.mkdir()
exe_copy = app_dir / EXE.name
shutil.copyfile(EXE, exe_copy)
assert exe_copy.is_file(), "exe copy failed"
out(f"[prep] app dir ready: {app_dir}")

(app_dir / "config.json").write_text(json.dumps({
    "workspaceFolder": str(ws_root),
    "mcpServers": {"workspace": {"command": "workspace_mcp.py", "args": []}},
}, indent=2), encoding="utf-8")

env = dict(os.environ, ZS_BRIDGE_PORT=str(PORT), ZS_WORKSPACE_ROOT=str(ws_root))
# stdin=DEVNULL is critical: if anything ever reaches an input() prompt, it gets
# EOF instead of blocking forever on the harness pipe.
proc = subprocess.Popen([str(exe_copy)], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                        errors="replace", env=env, cwd=str(app_dir),
                        stdin=subprocess.DEVNULL)

results = []


async def main():
    import websockets
    ws = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < 45:
        if proc.poll() is not None:
            break  # died early - bail out and dump output
        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{PORT}", max_size=16 * 1024 * 1024)
            break
        except Exception:
            await asyncio.sleep(0.7)
    if ws is None:
        results.append(("exe reachable (boot < 45s)", False))
        return
    out(f"[test] connected ({time.monotonic()-t0:.1f}s)")
    results.append(("exe reachable", True))
    rid = 0

    async def rpc(payload, timeout=30):
        nonlocal rid
        rid += 1
        payload["id"] = rid
        await ws.send(json.dumps(payload))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(payload.get("type"))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
            if msg.get("id") == rid:
                return msg

    # embedded worker up?
    ok_worker = False
    while time.monotonic() - t0 < 40 and proc.poll() is None:
        try:
            m = await rpc({"type": "studio_status"}, timeout=15)
        except (TimeoutError, asyncio.TimeoutError):
            continue
        if m.get("studio") is True:
            ok_worker = True
            break
        await asyncio.sleep(1)
    results.append(("embedded --workspace-worker up", ok_worker))
    if not ok_worker:
        return

    m = await rpc({"type": "list_tools"}, timeout=45)
    names = [t["name"] for t in m.get("tools", [])]
    results.append(("12 tools advertised", len(names) == 12))

    m = await rpc({"type": "call_tool", "name": "run_command",
                   "arguments": {"command": "echo hola-exe", "timeout_seconds": 15},
                   "timeout": 45000})
    results.append(("run_command via exe", m.get("ok") is True and "hola-exe" in m.get("text", "")))

    m = await rpc({"type": "call_tool", "name": "write_file",
                   "arguments": {"path": "from_exe.txt", "content": "escrito por el exe"},
                   "timeout": 30})
    results.append(("write_file via exe",
                    m.get("ok") is True and (ws_root / "from_exe.txt").is_file()))

    await ws.close()


try:
    asyncio.run(main())
finally:
    # The bridge spawns its own worker child which inherits the stdout pipe:
    # proc.terminate() would only kill the parent and leave the child holding
    # the pipe (and the port). Kill the WHOLE tree instead.
    was_alive = proc.poll() is None
    if was_alive:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
    try:
        txt = proc.communicate(timeout=15)[0]
    except Exception:
        txt = "(output unavailable - tree kill)"

print()
print("--- exe output (tail) ---")
lines = (txt or "").splitlines()
print("\n".join(lines[-14:]) if lines else "(empty)")
print()
fails = [n for n, ok in results if not ok]
for n, ok in results:
    print(f"[{'OK  ' if ok else 'FAIL'}] {n}")
sys.exit(1 if fails else 0)

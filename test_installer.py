# Installer verification: silent install -> run installed exe -> tree-kill -> silent uninstall.
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SETUP = ROOT / "installer" / "installer-output" / "OpenRender-Setup-0.0.1-beta.exe"
PORT = 17805

results = []


def check(name, ok):
    results.append((name, bool(ok)))
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}", flush=True)


def out(*a):
    print(*a, flush=True)


out(f"setup: {SETUP} ({SETUP.stat().st_size / 1024 / 1024:.1f} MB)")
check("installer exists", SETUP.is_file())

inst_dir = Path(tempfile.mkdtemp(prefix="or_inst_")) / "OpenRender"
res = subprocess.run([str(SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                      f"/DIR={inst_dir}"], timeout=180)
check("silent install exit 0", res.returncode == 0)
check("exe installed", (inst_dir / "OpenRender.exe").is_file())
check("extension installed", (inst_dir / "openrender-extension" / "manifest.json").is_file())
check("config installed", (inst_dir / "config.json").is_file())
cfg = json.loads((inst_dir / "config.json").read_text(encoding="utf-8"))
check("shipped config is clean", cfg.get("workspaceFolder") == "")

# Start-menu shortcut
sm = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "OpenRender.lnk"
check("start menu shortcut", sm.is_file())

# Boot the INSTALLED exe (env var avoids the folder picker), poke it, kill tree.
ws_root = Path(tempfile.mkdtemp(prefix="or_inst_ws_"))
env = dict(os.environ, ZS_BRIDGE_PORT=str(PORT), ZS_WORKSPACE_ROOT=str(ws_root))
proc = subprocess.Popen([str(inst_dir / "OpenRender.exe")], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                        errors="replace", env=env, cwd=str(inst_dir),
                        stdin=subprocess.DEVNULL)
import asyncio

booted = False


async def poke():
    import websockets
    # Onefile first-run extraction takes ~5s (sometimes more under AV scanning):
    # retry the connect instead of a single fixed sleep.
    ws = None
    for attempt in range(20):
        await asyncio.sleep(1.5)
        if proc.poll() is not None:
            out(f"   exe exited early rc={proc.returncode}")
            return False
        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{PORT}", open_timeout=5)
            break
        except Exception:
            continue
    if ws is None:
        out("   connect never worked")
        return False
    try:
        await ws.send(json.dumps({"type": "studio_status", "id": 1}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.monotonic())))
            if m.get("id") == 1:
                return m.get("studio") is True
        return False
    except Exception as e:
        out(f"   rpc failed: {type(e).__name__}: {e}")
        return False
    finally:
        try:
            await ws.close()
        except Exception:
            pass

try:
    booted = asyncio.run(poke())
finally:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
check("installed exe boots and serves", booted)
time.sleep(1)

# Silent uninstall
unins = inst_dir / "unins000.exe"
check("uninstaller exists", unins.is_file())
if unins.is_file():
    res = subprocess.run([str(unins), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                         timeout=180, cwd=str(inst_dir))
    time.sleep(2)
    check("exe removed by uninstall", not (inst_dir / "OpenRender.exe").is_file())
    check("config preserved after uninstall", (inst_dir / "config.json").is_file())

print()
fails = [n for n, ok in results if not ok]
sys.exit(1 if fails else 0)

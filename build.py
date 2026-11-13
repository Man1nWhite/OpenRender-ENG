# Build script for OpenRender Windows distribution.
#  - Converts assets/icon.png into build/icon.ico (PyInstaller needs .ico)
#  - Runs PyInstaller -> dist/OpenRender.exe (onefile, console app)
#  - Assembles release/OpenRender-<version>-win64.zip:
#      OpenRender.exe + openrender-extension/ + README.txt + clean config.json
# Usage:  python build.py            (build exe + zip)
#         python build.py --exe-only (skip the zip)
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
VERSION = "0.0.1-beta"
APP_NAME = "OpenRender"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
RELEASE = ROOT / "release"
EXT_SRC = ROOT / "openrender-extension"


def step(msg):
    print(f"\n=== {msg} " + "=" * max(0, 60 - len(msg)))


def make_icon():
    """assets/icon.png -> build/icon.ico with the standard size set."""
    from PIL import Image
    src = ROOT / "assets" / "icon.png"
    out = BUILD / "icon.ico"
    if not src.is_file():
        print("no assets/icon.png - building without a custom icon")
        return None
    img = Image.open(src).convert("RGBA")
    img.save(out, format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"icon: {out}")
    return out


def build_exe(icon):
    step("PyInstaller")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--name", APP_NAME,
        # workspace_mcp is imported dynamically in worker mode; make sure the
        # analysis always bundles it even if the literal import were refactored.
        "--hidden-import", "workspace_mcp",
        str(ROOT / "bridge.py"),
    ]
    if icon:
        # Must come AFTER "-m PyInstaller" - it is a PyInstaller flag, not a
        # python.exe flag.
        cmd.insert(3, f"--icon={icon}")
    print(" ".join(str(c) for c in cmd))
    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0 or not (DIST / f"{APP_NAME}.exe").is_file():
        print("FATAL: PyInstaller failed")
        sys.exit(1)
    exe = DIST / f"{APP_NAME}.exe"
    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"built: {exe} ({size_mb:.1f} MB)")
    return exe


def write_clean_config(stage: Path):
    """A fresh install ships an EMPTY workspace folder so the picker opens."""
    cfg = {"workspaceFolder": "", "mcpServers": {"workspace": {"command": "workspace_mcp.py", "args": []}}}
    (stage / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


README = f"""\
==========================================================
  {APP_NAME} {VERSION}  -  Quick guide (Windows)
==========================================================

WHAT IT IS
  An AI agent with full control of one folder on your PC:
  it reads, creates and edits files, searches content and
  runs terminal commands (install, build, tests, git...)
  from a normal DeepSeek, Gemini, Kimi, GLM, Qwen, Arena
  or Meta AI chat.

STEPS
  1) Double-click OpenRender.exe and choose your project
     FOLDER in the window that opens. Minimize the black
     window (do NOT close it).
  2) Load the extension in your browser (first time only):
       - Open chrome://extensions or edge://extensions
       - Turn on "Developer mode" (top-right corner)
       - "Load unpacked" -> select the
         "openrender-extension" folder next to this exe
         (with the installer: Documents\\OpenRender\\
          openrender-extension)
  3) Go to https://chat.deepseek.com (recommended), Gemini,
     Kimi, chat.z.ai, chat.qwen.ai or arena.ai and open a
     NEW chat.
  4) Click "Start agent" in the OpenRender bar and ask for
     whatever you want.

CHANGING FOLDER
  Close the bridge, open config.json (next to the exe) and
  clear the path saved in "workspaceFolder", or type another.

REQUIREMENTS
  - Windows 10/11 x64 (no Python needed: it is all bundled)
  - Chrome or Edge browser

NOTES
  - Everything is confined to your folder: it cannot touch
    anything outside it.
  - The AI keeps project notes in PROJECT_MEMORY.md inside
    your folder.
"""


def assemble_release(exe):
    step(f"Release zip")
    stage = RELEASE / APP_NAME
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(exe, stage / exe.name)
    write_clean_config(stage)
    (stage / "README.txt").write_text(README, encoding="utf-8", newline="\r\n")
    ext_dst = stage / EXT_SRC.name
    shutil.copytree(EXT_SRC, ext_dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    zip_path = RELEASE / f"{APP_NAME}-{VERSION}-windows-x64.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(stage):
            for f in files:
                full = Path(base) / f
                z.write(full, full.relative_to(stage.parent).as_posix())
    print(f"zip: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return zip_path


def main():
    BUILD.mkdir(exist_ok=True)
    icon = make_icon()
    exe = build_exe(icon)
    if "--exe-only" not in sys.argv:
        RELEASE.mkdir(exist_ok=True)
        assemble_release(exe)


if __name__ == "__main__":
    main()

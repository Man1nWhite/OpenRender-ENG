# Test harness: spawns workspace_mcp.py like bridge.py does and exercises every tool.
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SERVER = HERE / "workspace_mcp.py"

tmp = Path(tempfile.mkdtemp(prefix="zs_ws_test_"))
(tmp / "src").mkdir()
(tmp / "src" / "app.py").write_text("def main():\n    print('hello')\n\n\nif __name__ == '__main__':\n    main()\n", encoding="utf-8")
(tmp / "README.md").write_text("# Demo project\nA test workspace.\n", encoding="utf-8")

env = dict(os.environ, ZS_WORKSPACE_ROOT=str(tmp))
proc = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding="utf-8", env=env)
next_id = 1


def call(method, params=None, expect_reply=True):
    global next_id
    rid = next_id
    next_id += 1
    msg = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if not expect_reply:
        return None
    while True:
        line = proc.stdout.readline()
        if line == "":
            raise RuntimeError(f"server died. stderr:\n{proc.stderr.read()}")
        resp = json.loads(line)
        if resp.get("id") == rid:
            return resp


fails = []


def check(label, cond, extra=""):
    status = "OK  " if cond else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not cond:
        fails.append(label)


# Handshake
r = call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
check("initialize", "result" in r and r["result"]["serverInfo"]["name"] == "openrender-workspace")
call("notifications/initialized", {}, expect_reply=False)

# tools/list
r = call("tools/list")
names = [t["name"] for t in r["result"]["tools"]]
print("       tools:", ", ".join(names))
check("tools/list (12 tools)", len(names) == 12)

def tool(name, args):
    return call("tools/call", {"name": name, "arguments": args})

# workspace_info
r = tool("workspace_info", {})
txt = r.get("result", {}).get("content", [{}])[0].get("text", "")
check("workspace_info", "files" in txt and "src/" in txt and "README.md" in txt, f"| {txt.splitlines()[1]}")

# tree
r = tool("tree", {})
txt = r["result"]["content"][0]["text"]
check("tree", "app.py" in txt and "README.md" in txt and "src/" in txt)

# list_directory root + subdir
r = tool("list_directory", {})
check("list_directory root", "README.md" in r["result"]["content"][0]["text"])
r = tool("list_directory", {"path": "src"})
check("list_directory src", "app.py" in r["result"]["content"][0]["text"])

# read_file with numbers
r = tool("read_file", {"path": "src/app.py"})
txt = r["result"]["content"][0]["text"]
check("read_file numbered", "1 | def main():" in txt and "5 | " in txt)

# read_file offset/limit
r = tool("read_file", {"path": "src/app.py", "offset": 4, "limit": 2})
txt = r["result"]["content"][0]["text"]
check("read_file offset/limit", ("4 | " in txt) and ("6 | " not in txt))

# write_file new nested path
r = tool("write_file", {"path": "src/utils/helpers.js", "content": "export const add = (a, b) => a + b;\n"})
check("write_file creates parents", "Created" in r["result"]["content"][0]["text"])

# edit_file exact match
r = tool("edit_file", {"path": "src/app.py", "old_string": "print('hello')", "new_string": "print('hello world')"})
check("edit_file replace", "Edited" in r["result"]["content"][0]["text"])
r = tool("read_file", {"path": "src/app.py"})
check("edit_file persisted", "hello world" in r["result"]["content"][0]["text"])

# edit_file missing -> error
r = tool("edit_file", {"path": "src/app.py", "old_string": "this does not exist", "new_string": "x"})
check("edit_file missing errors", "error" in r and "not found" in r["error"]["message"])

# edit_file ambiguous
tool("write_file", {"path": "dup.txt", "content": "same line\nsame line\n"})
r = tool("edit_file", {"path": "dup.txt", "old_string": "same line", "new_string": "other"})
check("edit_file ambiguous errors", "error" in r and "2 places" in r["error"]["message"])

# edit_file replace_all
r = tool("edit_file", {"path": "dup.txt", "old_string": "same line", "new_string": "other", "replace_all": True})
check("edit_file replace_all", "2 occurrences" in r["result"]["content"][0]["text"])

# create_folder
r = tool("create_folder", {"path": "assets/img"})
check("create_folder", (tmp / "assets" / "img").is_dir())

# search_files glob
r = tool("search_files", {"pattern": "**/*.py"})
check("search_files", "app.py" in r["result"]["content"][0]["text"])

# grep_files text
r = tool("grep_files", {"query": "hello world"})
check("grep_files text", "app.py:2:" in r["result"]["content"][0]["text"], "| " + r["result"]["content"][0]["text"].splitlines()[1][:60])

# CRLF regression: edit a CRLF file with a multi-line old_string copied from
# read_file (LF-normalized). Must match, must not double the line endings.
crlf = tmp / "crlf.txt"
crlf.write_bytes(b"line one\r\nline two\r\nline three\r\n")
r = tool("edit_file", {"path": "crlf.txt", "old_string": "line one\nline two", "new_string": "LINE 1\nLINE 2"})
check("edit_file CRLF multi-line match", "Edited" in r["result"]["content"][0]["text"], "| " + r["result"]["content"][0]["text"])
raw = crlf.read_bytes()
check("CRLF endings preserved, no \\r\\r\\n", b"\r\n" in raw and b"\r\r\n" not in raw and b"LINE 1\r\nLINE 2" in raw)
r = tool("read_file", {"path": "crlf.txt"})
txt = r["result"]["content"][0]["text"]
check("read_file CRLF shows 3 clean lines", txt.count("\n") == 3 and "3 | line three" in txt)

# grep_files regex + include
r = tool("grep_files", {"query": r"const\s+add", "regex": True, "include": "**/*.js"})
check("grep_files regex+include", "helpers.js:1:" in r["result"]["content"][0]["text"])

# move_path rename
r = tool("move_path", {"source": "dup.txt", "destination": "renamed.txt"})
check("move_path rename", (tmp / "renamed.txt").exists() and not (tmp / "dup.txt").exists())

# move into folder
r = tool("move_path", {"source": "renamed.txt", "destination": "assets"})
check("move into folder", (tmp / "assets" / "renamed.txt").exists())

# delete file
r = tool("delete_path", {"path": "assets/renamed.txt"})
check("delete file", not (tmp / "assets" / "renamed.txt").exists())

# run_command (cross-platform: python -c)
py = sys.executable.replace("\\", "/")
r = tool("run_command", {"command": f'"{py}" -c "print(6*7)"'})
txt = r["result"]["content"][0]["text"]
check("run_command stdout", "exit code 0" in txt and "42" in txt)

# run_command failing exit code still returns result
r = tool("run_command", {"command": f'"{py}" -c "import sys; sys.exit(3)"'})
check("run_command nonzero reported", "exit code 3" in r["result"]["content"][0]["text"])

# SECURITY: escapes refused
r = tool("read_file", {"path": "../outside.txt"})
check("block ../ escape", "error" in r)
r = tool("read_file", {"path": str(Path(tmp.parent) / "evil.txt")})
check("block absolute outside", "error" in r and "relative" in r["error"]["message"])
r = tool("delete_path", {"path": "."})
check("refuse delete root", "error" in r and "root" in r["error"]["message"])
r = tool("write_file", {"path": "C:/Windows/evil.txt", "content": "x"})
check("block absolute write", "error" in r)

# unknown tool
r = tool("does_not_exist", {})
check("unknown tool errors", "error" in r)

proc.stdin.close()
proc.wait(timeout=5)
print()
print("Workspace used:", tmp)
if fails:
    print("FAILURES:", fails)
    sys.exit(1)
print("ALL TESTS PASSED")

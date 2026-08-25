#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# workspace_mcp.py
# ──────────────────────────────────────────────────────────────────────────
#  OpenRender Workspace MCP server.
#
#  A standalone MCP server (JSON-RPC over stdio, line-delimited) that gives
#  the AI FULL control over one local folder ("the workspace"):
#    - list / inspect the directory tree
#    - read and write files (with line numbers on read)
#    - exact-match string editing (old_string -> new_string)
#    - create / delete / move files and folders
#    - search by filename (glob) and by content (text or regex)
#    - run terminal commands inside the workspace (full control mode)
#
#  Every path is resolved against the workspace root; anything that escapes
#  it (absolute paths outside the root, ".." climbs) is refused. The root
#  itself can never be deleted or moved. Terminal commands run with the
#  workspace as the working directory and a hard timeout.
#
#  The workspace root comes from (in order):
#    1. ZS_WORKSPACE_ROOT environment variable (set by bridge.py)
#    2. The first CLI argument
#    3. The current working directory (fallback)
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "openrender-workspace"
SERVER_VERSION = "0.0.1"

# Output budget per tool result. Long enough for real work, small enough to
# keep a chat model's context (and the extension's composer) happy.
MAX_TEXT_CHARS = 40_000
MAX_READ_BYTES = 2 * 1024 * 1024          # refuse to slurp files beyond 2 MB
MAX_RUN_OUTPUT = 8_000                    # per-stream cap for command output
DEFAULT_RUN_TIMEOUT = 60                  # seconds
MAX_RUN_TIMEOUT = 600                     # seconds
GREP_MAX_RESULTS = 100
TREE_DEFAULT_DEPTH = 3
TREE_MAX_DEPTH = 8
IGNORED_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv",
                     ".idea", ".vscode", "dist", "build", ".next", "coverage"}

ROOT: Path = Path(".").resolve()


# ══════════════════════════════════════════════════════════════════════════
#  PATH SAFETY
# ══════════════════════════════════════════════════════════════════════════
class ToolError(Exception):
    """Raised by tool implementations; message goes back to the model."""


def resolve_path(rel: object, *, must_exist: bool = False) -> Path:
    """Resolve `rel` (a path relative to ROOT) and refuse any escape."""
    raw = str(rel if rel is not None else "").strip().replace("\\", "/")
    if raw in ("", ".", "/"):
        return ROOT
    raw = raw.lstrip("/")
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ToolError(f"paths must be relative to the workspace root, got '{raw}'")
    resolved = (ROOT / candidate).resolve()
    root_resolved = ROOT.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ToolError(f"path '{raw}' is outside the workspace")
    if must_exist and not resolved.exists():
        raise ToolError(f"'{raw}' does not exist in the workspace")
    return resolved


def rel_display(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT.resolve()).as_posix() or "."
    except ValueError:
        return p.as_posix()


# ══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════
def clip(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [output truncated at {limit} characters]"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n} B"


def read_text_file(path: Path) -> tuple[str, bool]:
    """Return (text, is_binary). Text is UTF-8 decoded with fallback."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1"), True
        except Exception:
            return "", True


def require_file(path: Path) -> None:
    if not path.exists():
        raise ToolError(f"'{rel_display(path)}' does not exist")
    if path.is_dir():
        raise ToolError(f"'{rel_display(path)}' is a folder, not a file")


def require_parent(path: Path) -> None:
    parent = path.parent.resolve()
    root_resolved = ROOT.resolve()
    if parent != root_resolved and root_resolved not in parent.parents:
        raise ToolError("cannot create entries outside the workspace")


def write_text_exact(path: Path, text: str) -> None:
    """Write text byte-for-byte with NO newline translation. Python's default
    text mode turns '\\n' into '\\r\\n' on Windows, so re-writing a CRLF file
    that was decoded verbatim would produce corrupted '\\r\\r\\n' sequences."""
    with open(path, "w", encoding="utf-8", errors="replace", newline="") as f:
        f.write(text)


def detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


# ══════════════════════════════════════════════════════════════════════════
#  TOOLS
# ══════════════════════════════════════════════════════════════════════════
def tool_workspace_info(args: dict) -> str:
    file_count = dir_count = 0
    total_size = 0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
        dir_count += len(dirs)
        for f in files:
            file_count += 1
            try:
                total_size += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    top = sorted(
        (e.name + ("/" if e.is_dir() else "") for e in ROOT.iterdir()),
        key=str.lower,
    )
    lines = [
        f"Workspace root: {ROOT}",
        f"Contents: {file_count} files, {dir_count} folders ({human_size(total_size)}) "
        "(common generated folders like node_modules/.git are excluded from counts)",
        "",
        "Top-level entries:",
    ]
    lines += [f"  {name}" for name in top[:100]] or ["  (empty folder)"]
    if len(top) > 100:
        lines.append(f"  ... and {len(top) - 100} more (use list_directory)")
    return "\n".join(lines)


def tool_list_directory(args: dict) -> str:
    p = resolve_path(args.get("path"), must_exist=True)
    if not p.is_dir():
        raise ToolError(f"'{rel_display(p)}' is a file, not a folder")
    entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    if not entries:
        return f"{rel_display(p)}/ is empty."
    lines = []
    for e in entries[:500]:
        if e.is_dir():
            try:
                n = sum(1 for _ in e.iterdir())
            except OSError:
                n = 0
            lines.append(f"  [dir ] {e.name}/ ({n} items)")
        else:
            try:
                size = e.stat().st_size
                lines.append(f"  [file] {e.name} ({human_size(size)})")
            except OSError:
                lines.append(f"  [file] {e.name}")
    if len(entries) > 500:
        lines.append(f"  ... and {len(entries) - 500} more")
    return f"{rel_display(p)}/:\n" + "\n".join(lines)


def tool_tree(args: dict) -> str:
    p = resolve_path(args.get("path"), must_exist=True)
    depth = args.get("depth", TREE_DEFAULT_DEPTH)
    try:
        depth = max(1, min(int(depth), TREE_MAX_DEPTH))
    except (TypeError, ValueError):
        depth = TREE_DEFAULT_DEPTH
    out_lines: list[str] = [f"{rel_display(p) or '.'}/"]

    def walk(d: Path, prefix: str, level: int) -> None:
        if level > depth:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        visible = [e for e in entries if e.is_file() or e.name not in IGNORED_DIR_NAMES]
        for i, e in enumerate(visible):
            last = i == len(visible) - 1
            branch = "`-- " if last else "|-- "
            if e.is_dir():
                out_lines.append(f"{prefix}{branch}{e.name}/")
                walk(e, prefix + ("    " if last else "|   "), level + 1)
            else:
                out_lines.append(f"{prefix}{branch}{e.name}")

    walk(p, "", 1)
    text = "\n".join(out_lines)
    if len(out_lines) > 1500:
        text = clip(text, 30_000) + "\n... [tree truncated - use list_directory or a deeper/narrower path]"
    return text


def tool_read_file(args: dict) -> str:
    p = resolve_path(args.get("path"), must_exist=True)
    require_file(p)
    size = p.stat().st_size
    if size > MAX_READ_BYTES:
        raise ToolError(
            f"'{rel_display(p)}' is {human_size(size)} - too large to read whole "
            f"(limit {human_size(MAX_READ_BYTES)}). Read it in parts with offset/limit "
            "if you really need to, or grep_files to find the relevant section.")
    text, binary = read_text_file(p)
    if binary:
        return f"{rel_display(p)} looks like a BINARY file ({human_size(size)}); its content is not shown as text."
    lines = text.splitlines()
    total = len(lines)
    try:
        start = int(args.get("offset", 1) or 1)
    except (TypeError, ValueError):
        start = 1
    start = max(1, start)
    try:
        limit = int(args.get("limit", 2000) or 2000)
    except (TypeError, ValueError):
        limit = 2000
    limit = max(1, min(limit, 4000))
    chunk = lines[start - 1:start - 1 + limit]
    header = f"{rel_display(p)}  ({total} line{'s' if total != 1 else ''}, {human_size(size)})"
    if not chunk:
        return f"{header}\n(no lines in range {start}-{start + limit - 1})"
    body = "\n".join(f"{start + i:>5} | {ln}" for i, ln in enumerate(chunk))
    footer = ""
    end = start - 1 + len(chunk)
    if end < total:
        footer = f"\n... lines {end + 1}-{total} continue (use offset={end + 1})"
    return clip(f"{header}\n{body}{footer}")


def tool_write_file(args: dict) -> str:
    rel = args.get("path")
    if not rel or not str(rel).strip():
        raise ToolError("'path' is required")
    content = args.get("content")
    if content is None:
        raise ToolError("'content' is required (use \"\" for an empty file)")
    if not isinstance(content, str):
        raise ToolError("'content' must be a string")
    p = resolve_path(rel)
    existed = p.exists()
    if existed and p.is_dir():
        raise ToolError(f"'{rel_display(p)}' is a folder - cannot overwrite it with a file")
    require_parent(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_text_exact(p, content)
    action = "overwrote" if existed else "created"
    n_lines = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
    return f"{action.capitalize()} {rel_display(p)} ({len(content)} chars, ~{n_lines} lines)."


def tool_edit_file(args: dict) -> str:
    rel = args.get("path")
    if not rel or not str(rel).strip():
        raise ToolError("'path' is required")
    old = args.get("old_string")
    new = args.get("new_string")
    if old is None or new is None:
        raise ToolError("'old_string' and 'new_string' are required")
    if not isinstance(old, str) or not isinstance(new, str):
        raise ToolError("'old_string' and 'new_string' must be strings")
    if old == new:
        raise ToolError("old_string and new_string are identical - nothing to change")
    replace_all = bool(args.get("replace_all", False))
    p = resolve_path(rel, must_exist=True)
    require_file(p)
    size = p.stat().st_size
    if size > MAX_READ_BYTES:
        raise ToolError(f"'{rel_display(p)}' is too large to edit ({human_size(size)})")
    text, _binary = read_text_file(p)
    # Match in LF-normalized space (what read_file displays) but preserve the
    # file's own line endings on write, so a CRLF file stays CRLF and a
    # multi-line old_string copied from read_file still matches byte-for-byte.
    eol = detect_eol(text)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    old_norm = old.replace("\r\n", "\n").replace("\r", "\n")
    new_norm = new.replace("\r\n", "\n").replace("\r", "\n")
    count = normalized.count(old_norm)
    if count == 0:
        probe = old_norm[:60]
        near = normalized.find(probe)
        hint = ""
        if near != -1:
            window = normalized[near:near + len(old_norm)]
            diff_at = next((i for i, (a, b) in enumerate(zip(window, old_norm)) if a != b), min(len(window), len(old_norm)))
            hint = (f" A similar passage exists around character {near}: your old_string first differs "
                    f"at position {diff_at}. Re-read the file with read_file and copy the EXACT text.")
        raise ToolError(f"old_string not found in {rel_display(p)} (searched verbatim).{hint}")
    if count > 1 and not replace_all:
        snippet = old_norm.strip().splitlines()[0][:60] if old_norm.strip() else ""
        raise ToolError(
            f"old_string matches {count} places in {rel_display(p)}. Add surrounding context so it is UNIQUE, "
            f"or pass replace_all:true to change every occurrence.{f' First line: {snippet}' if snippet else ''}")
    occurrences = count if replace_all else 1
    new_normalized = (normalized.replace(old_norm, new_norm) if replace_all
                      else normalized.replace(old_norm, new_norm, 1))
    if eol != "\n":
        new_text = new_normalized.replace("\n", eol)
    else:
        new_text = new_normalized
    write_text_exact(p, new_text)
    where = f"{count} occurrences" if replace_all else "first occurrence"
    return f"Edited {rel_display(p)}: replaced {where} of old_string ({len(old)} chars -> {len(new)} chars)."


def tool_create_folder(args: dict) -> str:
    rel = args.get("path")
    if not rel or not str(rel).strip():
        raise ToolError("'path' is required")
    p = resolve_path(rel)
    require_parent(p)
    if p.exists() and p.is_file():
        raise ToolError(f"'{rel_display(p)}' exists as a FILE - cannot create a folder with that name")
    p.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {rel_display(p)}/"


def tool_delete_path(args: dict) -> str:
    rel = args.get("path")
    if not rel or not str(rel).strip():
        raise ToolError("'path' is required")
    p = resolve_path(rel, must_exist=True)
    if p == ROOT.resolve():
        raise ToolError("refusing to delete the workspace root itself")
    display = rel_display(p)
    if p.is_dir():
        try:
            n = sum(len(files) for _, _, files in os.walk(p))
        except OSError:
            n = 0
        shutil.rmtree(p)
        return f"Deleted folder {display}/ ({n} files removed)."
    p.unlink()
    return f"Deleted file {display}."


def tool_move_path(args: dict) -> str:
    src = resolve_path(args.get("source"), must_exist=True)
    if src == ROOT.resolve():
        raise ToolError("refusing to move the workspace root itself")
    dst_rel = args.get("destination")
    if not dst_rel or not str(dst_rel).strip():
        raise ToolError("'destination' is required")
    dst = resolve_path(dst_rel)
    require_parent(dst)
    if dst.exists() and dst.is_dir():
        dst = dst / src.name  # move INTO the given folder
    if dst.exists():
        raise ToolError(f"destination '{rel_display(dst)}' already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved {rel_display(src)} -> {rel_display(dst)}."


def tool_search_files(args: dict) -> str:
    pattern = str(args.get("pattern", "") or "").strip()
    if not pattern:
        raise ToolError("'pattern' is required, e.g. \"**/*.py\"")
    matches: list[str] = []
    try:
        for m in ROOT.glob(pattern):
            rel = rel_display(m)
            tag = "dir/" if m.is_dir() else ""
            matches.append(f"  {rel}{tag}")
            if len(matches) >= GREP_MAX_RESULTS:
                break
    except (OSError, ValueError) as e:
        raise ToolError(f"invalid pattern '{pattern}': {e}")
    if not matches:
        return f"No paths match \"{pattern}\"."
    tail = "" if len(matches) < GREP_MAX_RESULTS else f"\n  ... stopped at {GREP_MAX_RESULTS} results"
    return f"Paths matching \"{pattern}\" ({len(matches)}):\n" + "\n".join(matches) + tail


def tool_grep_files(args: dict) -> str:
    query = args.get("query")
    if query is None or str(query) == "":
        raise ToolError("'query' is required")
    include = str(args.get("include", "**/*") or "**/*")
    is_regex = bool(args.get("regex", False))
    try:
        flags = re.IGNORECASE if args.get("ignore_case", True) else 0
        rx = re.compile(str(query), flags) if is_regex else None
    except re.error as e:
        raise ToolError(f"invalid regex '{query}': {e}")
    needle = str(query).lower()

    hits: list[str] = []
    scanned = 0
    try:
        candidates = [c for c in ROOT.glob(include) if c.is_file()]
    except (OSError, ValueError):
        candidates = [c for c in ROOT.rglob("*") if c.is_file()]
    for path in candidates:
        if len(hits) >= GREP_MAX_RESULTS:
            break
        try:
            if path.stat().st_size > MAX_READ_BYTES:
                continue
            text, binary = read_text_file(path)
            if binary:
                continue
        except OSError:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            ok = bool(rx.search(line)) if rx else needle in line.lower()
            if ok:
                rel = rel_display(path)
                hits.append(f"  {rel}:{lineno}: {line.strip()[:160]}")
                if len(hits) >= GREP_MAX_RESULTS:
                    break
    if not hits:
        kind = "regex" if is_regex else "text"
        return f"No matches for {kind} \"{query}\" (scanned {scanned} files matching \"{include}\")."
    tail = "" if len(hits) < GREP_MAX_RESULTS else f"\n  ... stopped at {GREP_MAX_RESULTS} matches"
    return f"Matches for \"{query}\" ({len(hits)}, scanned {scanned} files):\n" + "\n".join(hits) + tail


def tool_run_command(args: dict) -> str:
    command = str(args.get("command", "") or "").strip()
    if not command:
        raise ToolError("'command' is required, e.g. \"python main.py\" or \"npm install\"")
    try:
        timeout = int(args.get("timeout_seconds", DEFAULT_RUN_TIMEOUT) or DEFAULT_RUN_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_RUN_TIMEOUT
    timeout = max(1, min(timeout, MAX_RUN_TIMEOUT))
    shell = os.name == "nt"
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=shell,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (f"Command TIMED OUT after {timeout}s: {command}\n"
                "It may still have had partial effects. For long-running servers/tests, "
                "run them differently (background job, shorter test subset) instead of blocking.")
    except OSError as e:
        raise ToolError(f"could not run command: {e}")
    elapsed = time.monotonic() - t0
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if len(out) > MAX_RUN_OUTPUT:
        out = out[:MAX_RUN_OUTPUT] + f"\n... [stdout truncated at {MAX_RUN_OUTPUT} chars]"
    if len(err) > MAX_RUN_OUTPUT:
        err = err[:MAX_RUN_OUTPUT] + f"\n... [stderr truncated at {MAX_RUN_OUTPUT} chars]"
    parts = [
        f"$ {command}",
        f"(ran in the workspace root, exit code {proc.returncode}, {elapsed:.1f}s)",
    ]
    if out:
        parts += ["", "--- stdout ---", out]
    if err:
        parts += ["", "--- stderr ---", err]
    if proc.returncode != 0 and not err:
        parts += ["", "(non-zero exit code with empty stderr - check stdout above)"]
    return clip("\n".join(parts))


# ══════════════════════════════════════════════════════════════════════════
#  TOOL SCHEMAS (MCP tools/list payload)
# ══════════════════════════════════════════════════════════════════════════
S = {"type": "object", "properties": {}, "required": []}


def schema(props: dict, req: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": req}


TOOLS = [
    {
        "name": "workspace_info",
        "description": ("Overview of the connected project folder: absolute root path, file/folder counts, "
                        "total size and top-level entries. Call this once when you need orientation."),
        "inputSchema": S,
    },
    {
        "name": "list_directory",
        "description": "List one folder's entries with types and sizes.",
        "inputSchema": schema({
            "path": {"type": "string", "description": "Folder path relative to the workspace root. Empty = root."},
        }, []),
    },
    {
        "name": "tree",
        "description": ("Recursive directory tree (folders + files). Great first step to understand a project's layout. "
                        "Common generated folders (.git, node_modules, __pycache__, .venv, dist...) are skipped."),
        "inputSchema": schema({
            "path": {"type": "string", "description": "Subtree root, relative to the workspace root. Empty = root."},
            "depth": {"type": "integer", "description": f"Max depth 1-{TREE_MAX_DEPTH}. Default {TREE_DEFAULT_DEPTH}."},
        }, []),
    },
    {
        "name": "read_file",
        "description": ("Read a text file. Returns numbered lines as 'LINE | content'. Always read a file before "
                        "editing it, so your old_string matches byte-for-byte."),
        "inputSchema": schema({
            "path": {"type": "string", "description": "File path relative to the workspace root."},
            "offset": {"type": "integer", "description": "First line to show (1-based). Default 1."},
            "limit": {"type": "integer", "description": "Max lines to return (max 4000). Default 2000."},
        }, ["path"]),
    },
    {
        "name": "write_file",
        "description": ("Create a file or OVERWRITE an existing one with complete new content. Parent folders are "
                        "created automatically. For partial changes prefer edit_file."),
        "inputSchema": schema({
            "path": {"type": "string", "description": "File path relative to the workspace root."},
            "content": {"type": "string", "description": "Full file content. Use \"\" for an empty file."},
        }, ["path", "content"]),
    },
    {
        "name": "edit_file",
        "description": ("Exact-match string replacement inside a file. old_string must match the current content "
                        "byte-for-byte (copy it from read_file). Replaces the FIRST match, or every match with "
                        "replace_all:true. Fails loudly when old_string is missing or ambiguous."),
        "inputSchema": schema({
            "path": {"type": "string"},
            "old_string": {"type": "string", "description": "Exact existing text to replace."},
            "new_string": {"type": "string", "description": "Replacement text."},
            "replace_all": {"type": "boolean", "description": "Replace every occurrence instead of just the first."},
        }, ["path", "old_string", "new_string"]),
    },
    {
        "name": "create_folder",
        "description": "Create a folder (and parents).",
        "inputSchema": schema({
            "path": {"type": "string"},
        }, ["path"]),
    },
    {
        "name": "delete_path",
        "description": ("Permanently DELETE a file or folder (folders recursively). Destructive: confirm scope with "
                        "the user before deleting anything broad, and never delete the workspace root."),
        "inputSchema": schema({
            "path": {"type": "string"},
        }, ["path"]),
    },
    {
        "name": "move_path",
        "description": ("Move or rename a file/folder. If destination is an existing folder, the source is moved "
                        "INSIDE it keeping its name."),
        "inputSchema": schema({
            "source": {"type": "string"},
            "destination": {"type": "string"},
        }, ["source", "destination"]),
    },
    {
        "name": "search_files",
        "description": ("Find files/folders by NAME using glob patterns, e.g. \"**/*.py\", \"src/**/*.js\", "
                        "\"**/config*.json\"."),
        "inputSchema": schema({
            "pattern": {"type": "string", "description": "Glob pattern relative to the workspace root."},
        }, ["pattern"]),
    },
    {
        "name": "grep_files",
        "description": ("Search INSIDE file contents across the workspace. Case-insensitive substring by default; "
                        "set regex:true for regular expressions. Narrow with include globs like \"src/**/*.ts\"."),
        "inputSchema": schema({
            "query": {"type": "string", "description": "Text or regex to find."},
            "include": {"type": "string", "description": "Glob limiting which files are scanned. Default all."},
            "regex": {"type": "boolean", "description": "Treat query as a regular expression."},
            "ignore_case": {"type": "boolean", "description": "Case-insensitive. Default true."},
        }, ["query"]),
    },
    {
        "name": "run_command",
        "description": ("Run a terminal command in the workspace root (full control): install dependencies, build, "
                        "test, use git, compile, etc. Captures stdout/stderr and the exit code. Blocking call - "
                        "it finishes before returning (hard timeout). Do NOT start interactive apps or dev servers."),
        "inputSchema": schema({
            "command": {"type": "string", "description": "The shell command to run."},
            "timeout_seconds": {"type": "integer", "description":
                                f"Timeout in seconds (default {DEFAULT_RUN_TIMEOUT}, max {MAX_RUN_TIMEOUT})."},
        }, ["command"]),
    },
]

_DISPATCH = {
    "workspace_info": tool_workspace_info,
    "list_directory": tool_list_directory,
    "tree": tool_tree,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "create_folder": tool_create_folder,
    "delete_path": tool_delete_path,
    "move_path": tool_move_path,
    "search_files": tool_search_files,
    "grep_files": tool_grep_files,
    "run_command": tool_run_command,
}


# ══════════════════════════════════════════════════════════════════════════
#  JSON-RPC LOOP (stdio, line-delimited - exactly what bridge.py speaks)
# ══════════════════════════════════════════════════════════════════════════
def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(mid, payload: dict) -> None:
    _send({"jsonrpc": "2.0", "id": mid, "result": payload})


def _error(mid, message: str, code: int = -32000) -> None:
    if mid is None:
        return
    _send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})


def handle(msg: dict) -> None:
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        _result(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
        return

    if method == "tools/list":
        _result(mid, {"tools": TOOLS})
        return

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        fn = _DISPATCH.get(name)
        if fn is None:
            _error(mid, f"unknown tool '{name}'")
            return
        try:
            text = fn(args if isinstance(args, dict) else {})
        except ToolError as e:
            _error(mid, str(e))
            return
        except Exception as e:  # never crash the loop on a bad call
            _error(mid, f"internal error running '{name}': {type(e).__name__}: {e}")
            return
        _result(mid, {"content": [{"type": "text", "text": text}]})
        return

    # notifications (notifications/initialized etc.) and unknown methods.
    if mid is not None:
        _error(mid, f"method not found: {method}", code=-32601)


def main() -> int:
    global ROOT
    chosen = os.environ.get("ZS_WORKSPACE_ROOT") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not chosen:
        chosen = os.getcwd()
    ROOT = Path(chosen).expanduser().resolve()
    if not ROOT.is_dir():
        sys.stderr.write(f"workspace_mcp: workspace root is not a folder: {ROOT}\n")
        return 1
    sys.stderr.write(f"workspace_mcp: serving {ROOT}\n")
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                try:
                    handle(msg)
                except Exception as e:
                    mid = msg.get("id") if isinstance(msg, dict) else None
                    _error(mid, f"handler error: {type(e).__name__}: {e}")
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

# OpenRender

> **Your favorite chat AI, with full control of one folder on your PC.**
> Turn DeepSeek, Gemini, Kimi, GLM, Qwen, Arena or Meta AI into a real agent that reads, creates and edits files, searches the code and runs terminal commands — all inside the folder you choose.

**Version:** 0.0.1 beta · **Platform:** Windows · **License:** GPL-3.0

---

## 📖 Table of contents

1. [What it is and what it does](#-what-it-is-and-what-it-does)
2. [How it works (architecture)](#-how-it-works-architecture)
3. [Installation for users](#-installation-for-users)
4. [Daily use](#-daily-use)
5. [The agent's 12 commands](#-the-agents-12-commands)
6. [Security: what it can and cannot do](#-security)
7. [Project structure](#-project-structure)
8. [Building from source](#-building-from-source)
9. [Tests](#-tests)
10. [Advanced configuration](#-advanced-configuration)
11. [Troubleshooting](#-troubleshooting)
12. [Roadmap and limitations](#-roadmap-and-limitations)
13. [Credits and license](#-credits-and-license)

---

## 🤖 What it is and what it does

Web AI models (DeepSeek, Gemini…) are excellent at programming, but **they cannot touch your disk**: they only write text that you have to copy and paste file by file.

**OpenRender closes that gap.** It is a bridge between the chat and your disk:

- The model writes **JSON commands** inside its normal reply (`{"command": "edit_file", ...}`)
- The **browser extension** detects those commands in the chat page
- The **local bridge** (`OpenRender.exe`) runs them against your folder
- The result goes back to the chat as another message, and the AI carries on by itself

The result: you ask *"fix the login bug and run the tests"* and the AI explores the project, reads the files, applies the changes, runs `npm test` and reports back — without you touching the keyboard.

### Features

| | |
|---|---|
| 📁 Full control of ONE folder | Read, create, edit, delete, move — confined to it |
| 💻 Built-in terminal | Install dependencies, build, run tests, use git |
| 🔎 Real search | By name (glob) and by content (text or regex) |
| 🧠 Persistent memory | Project notes in `PROJECT_MEMORY.md` across sessions |
| 🗂️ Multi-project | Folder history with 1-click switching from the chat |
| 🔌 No API keys | Uses the free chat websites you already know |
| 🔒 Sandboxed | Nothing outside the chosen folder; broad deletions ask for confirmation |
| ➕ Extensible via MCP | Add other MCP servers (Blender, etc.) as addons |

---

## ⚙️ How it works (architecture)

```
┌─────────────────────────┐
│  Web chat (DeepSeek,    │   The model replies with text +
│  Gemini, Kimi, GLM,     │   JSON commands inside code
│  Qwen, Arena, Meta AI)  │   blocks
└───────────┬─────────────┘
            │  the extension reads the page (DOM)
┌───────────▼─────────────┐
│  Chrome/Edge extension  │   openrender-extension/
│  - agentic loop         │   parser → executor → feedback
│  - UI: bar, chips,      │
│    folder menu          │
└───────────┬─────────────┘
            │  WebSocket ws://127.0.0.1:17613
┌───────────▼─────────────┐
│  Local bridge           │   bridge.py  →  dist/OpenRender.exe
│  - spawns MCP servers   │   (PyInstaller: Python bundled)
│  - routes each command  │
│  - folder picker        │
└───────────┬─────────────┘
            │  stdio (JSON-RPC, MCP protocol)
┌───────────▼─────────────┐
│  Workspace server       │   workspace_mcp.py
│  (embedded in the exe)  │   12 tools over YOUR folder
└───────────┬─────────────┘
            ▼
   📂 Documents/my-project/
```

**Flow of a command:**

1. You ask for something in the chat.
2. The AI replies with a ```json``` block such as `{"command": "read_file", "params": {"path": "src/app.py"}}`.
3. The extension parses it (`core/parser.js`), validates it against the tool catalog and sends it to the bridge over WebSocket (`background.js`).
4. The bridge routes it to the right server and waits for the result (with retries, watchdogs and auto-restart if the server died).
5. The result goes back to the chat as a user message ("Output of 'read_file': …"), visually disguised as a card.
6. The AI reads it and decides the next step. And so on until it is done.

Everything is **local**: neither your code nor your folder leaves your machine (only what the AI explicitly reads travels to the chat, just as if you pasted the files by hand).

---

## 🚀 Installation for users

> **Requirements:** Windows 10/11 x64 + Chrome or Edge. No Python or anything else needed (everything is inside the exe).

### Option A — Installer (recommended)

1. Download and run **`OpenRender-Setup-0.0.1-beta.exe`**
2. Next → Next. It installs into **`Documents\OpenRender`**:
   ```
   Documents\OpenRender\
   ├── OpenRender.exe          ← the program
   ├── openrender-extension\   ← the extension
   └── README.txt              ← quick guide
   ```
   With shortcuts on the desktop and in the Start menu.

### Option B — Portable

Download `OpenRender-0.0.1-beta-windows-x64.zip` and unzip it wherever you like. Same contents.

> ℹ️ Windows will show a blue warning ("Windows protected your PC") because the exe is not digitally signed: **More info → Run anyway**.

### First run (guided)

When you open `OpenRender.exe` for the first time, a **3-step tutorial** appears:

1. **Load the extension** (one time only): `chrome://extensions` → *Developer mode* → *Load unpacked* → select the `openrender-extension` folder. The tutorial offers to open that folder for you automatically.
2. Type **`y` (Ready)** → the picker opens so you can choose **your project folder**.
3. Done. From then on it starts straight away with the saved folder.

---

## 🖱️ Daily use

| Step | Action |
|---|---|
| 1 | Open **OpenRender.exe** (minimize the black window — it is the bridge) |
| 2 | Go to [chat.deepseek.com](https://chat.deepseek.com) *(recommended)*, Gemini, [kimi.com](https://www.kimi.com), [chat.z.ai](https://chat.z.ai), [chat.qwen.ai](https://chat.qwen.ai) or [arena.ai](https://arena.ai) |
| 3 | Open a **new** chat → click **▶ Start agent** in the green bar above the text box |
| 4 | Ask for whatever you want. Each operation shows up as a card in the chat |

Examples of real requests:

```
"Explore the project and explain how it is structured"
"Add validation to the sign-up form and check that it works"
"This test fails: find out why and fix it"
"Create a /api/users endpoint with tests"
"Push all the changes to a new branch"
"Rename the function process() to process_order() across the whole project"
```

**The bar's ⌄ panel:** switch working folder (1-click history), **+ Add folder** (native picker), switch AI, custom prompt, manage addon MCP servers.

**Switching project:** you can also click another folder in the history at any time — the AI starts working there instantly and the previous one is out of its reach.

---

## 🛠️ The agent's 12 commands

The AI can only use these commands (it discovers them with `list_commands` at startup):

| Command | What it does |
|---|---|
| `workspace_info` | Overview: root path, file count, top-level entries |
| `tree` | Recursive directory tree (ignores `node_modules`, `.git`, etc.) |
| `list_directory` | Listing of a folder with sizes |
| `read_file` | Reads a file with numbered lines (paginated with offset/limit) |
| `write_file` | Creates a file or overwrites it entirely |
| `edit_file` | Exact diff-style replacement: `old_string` → `new_string` (+ `replace_all`) |
| `create_folder` | Creates folders (with parents) |
| `delete_path` | Deletes files/folders (destructive, asks for confirmation on broad scope) |
| `move_path` | Move or rename |
| `search_files` | Searches by name with globs (`**/*.py`, `src/**/*.js`…) |
| `grep_files` | Searches INSIDE files (text or regex, filterable by glob) |
| `run_command` | Runs terminal commands at the root (configurable timeout) |

It also keeps **persistent memory** in `PROJECT_MEMORY.md`: architecture, conventions, decisions and user preferences, shared across all sessions.

---

## 🔒 Security

- **Strict sandbox:** every path is resolved inside the chosen folder. `../`, external absolute paths and links pointing outside → rejected. The root can never be deleted or moved.
- **Protected deletions:** `delete_path` is permanent; the system prompt instructs the AI to confirm with you before any deletion beyond what you explicitly asked for.
- **Localhost only:** the bridge listens on `127.0.0.1:17613`; nothing is exposed to the network.
- **You choose the folder:** the AI only sees what is inside it. Switching project = switching its world.
- **Open source:** everything it runs is in this repo, auditable line by line.

Even so: this is a beta with real control over your disk. **Use git**, review what it does and do not give it folders containing secrets (.env, keys) unless you need to.

---

## 📂 Project structure

```
OpenRender/
├── bridge.py                    # WebSocket ↔ MCP servers (stdio) bridge
│                                # - folder picker/tutorial (first run)
│                                # - hot folder switching (from the chat)
│                                # - server auto-restart, watchdogs
│                                # - packaged mode: re-spawns itself as worker
├── workspace_mcp.py             # Main MCP server: 12 file+terminal tools
│                                # over the chosen folder
├── config.json                  # Local state (active folder, history) - NOT committed
├── config.example.json          # Configuration template
├── start.bat / MacOS_Start.command  # Launchers for development (no exe)
│
├── openrender-extension/        # Browser extension (Chrome/Edge, MV3)
│   ├── manifest.json
│   ├── background.js            # WebSocket to the bridge + state cache
│   ├── core/
│   │   ├── main.js              # Agentic loop + UI (bar, chips, menu)
│   │   ├── parser.js            # JSON command parser (Markdown-tolerant)
│   │   └── config.js            # System prompt + tool notes
│   ├── providers/               # One DOM adapter per chat site:
│   │   ├── deepseek.js          #   deepseek.js, gemini.js, kimi.js, glm.js,
│   │   ├── gemini.js            #   qwen.js(+qwen-net.js), arena.js, meta.js
│   │   └── …                    #   (selectors, sending, generation detection)
│   ├── overlay.css              # Bar/chips/menu styles
│   └── popup.html/js            # Icon popup: bridge status
│
├── build.py                     # Packages the exe (PyInstaller) + portable zip
├── build_installer.bat          # Compiles the installer (Inno Setup)
├── installer/OpenRender-installer.iss
│
├── test_workspace_mcp.py        # 30 tests of the file server
├── test_bridge_e2e.py           # Full bridge over WebSocket (13 checks)
├── test_exe_e2e.py              # The packaged exe, end-to-end
└── test_installer.py            # Install→launch→uninstall of the setup
```

**Key design details:**

- **Standard MCP protocol** (JSON-RPC over stdio): any MCP server can be added as an addon from the panel; the bridge aggregates its tools and routes by name.
- **One exe, two roles:** in packaged mode, `bridge.py` re-spawns itself with `--workspace-worker` to serve the embedded workspace.
- **Provider pattern:** `core/main.js` never touches the chat's DOM; each site has its own adapter. Adding a new AI = one new file in `providers/`.
- **Loop anti-fragility:** hard timeouts on every call, retries on transient failures, command deduplication after reloads, automatic pause when the tab loses focus.

---

## 🔨 Building from source

Requirements: Python 3.9+ and `pip install pyinstaller pillow`.

```bat
python build.py             rem → dist\OpenRender.exe + release\*.zip
build_installer.bat         rem → installer-output\OpenRender-Setup-*.exe (requires Inno Setup, free)
```

To try it in development without packaging: `start.bat` (finds Python by itself, installs `websockets` if missing).

---

## ✅ Tests

```bat
python test_workspace_mcp.py   rem MCP protocol: 30 tests (CRUD, grep, CRLF safety…)
python test_bridge_e2e.py      rem real bridge startup + hot folder switching
python test_exe_e2e.py         rem the same against dist\OpenRender.exe
python test_installer.py       rem silent install → launch → uninstall
node test-parser.js            rem (in openrender-extension\) command parser
```

---

## ⚙️ Advanced configuration

**`config.json`** (next to the exe; see `config.example.json`):

```json
{
  "workspaceFolder": "D:\\projects\\my-app",   // active folder ("" = ask)
  "workspaceHistory": ["D:\\projects\\my-app"], // menu history (max 8)
  "mcpServers": {
    "workspace": { "command": "workspace_mcp.py", "args": [] },
    "blender":   { "command": "npx", "args": ["-y", "@some/mcp-blender"] }
  }
}
```

| Environment variable | Effect |
|---|---|
| `ZS_WORKSPACE_ROOT` | Forces the working folder (skips the picker) |
| `ZS_BRIDGE_PORT`    | Changes the bridge port (default `17613`) |

**Adding another MCP server** (Blender, Sketchfab…): ⌄ panel → *MCP servers* → name + start command. The bridge restarts and its tools appear alongside the workspace ones.

---

## 🩺 Troubleshooting

| Symptom | Solution |
|---|---|
| Gray "Bridge offline" bar | The black window is closed → open `OpenRender.exe` |
| Yellow dot | The bridge is alive but there is no folder yet → check the black window |
| The AI replies in plain text, without commands | Remind it to use the commands, or open a new chat and Start agent |
| Occasional "No response from server" | Retry; the bridge retries by itself on brief failures |
| I want a different folder | ⌄ panel → Project folder → click another one or "+ Add folder" |
| Port in use | Close any other open OpenRender, or `set ZS_BRIDGE_PORT=17614` before opening |

Detailed logs: the bridge window and `logs\bridge_debug.log` (next to the exe).

---

## 🗺️ Roadmap and limitations

**Current beta (0.0.1):** Windows only · the extension must be loaded by hand (Chrome/Edge do not allow installing extensions from external programs) · Gemini/Kimi can be unstable in long sessions (on Arena use **Direct** mode) · `run_command` blocks for up to 10 min maximum.

**Ideas in the queue:** digitally signed installer · publishing on the Chrome Web Store · macOS/Linux version of the exe · streaming the output of long commands · selecting multiple folders at once.

---

## 💬 Credits and license

OpenRender is a heavily reworked fork of [ZeroScript Free](https://github.com/sebattfg/ZeroScript-Free) (from a Roblox Studio agent to a local-folder agent), which in turn borrows MCP-addon connection ideas from [javnpa](https://github.com/javnpa). Thanks to both. 🙏

**GPL-3.0** license — see [LICENSE](LICENSE). Use it, modify it and share it freely.

---
*Made with ❤️ to stop copying and pasting code by hand.*

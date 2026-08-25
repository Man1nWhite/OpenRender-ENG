# OpenRender - AI Agent for your Project Folder (DeepSeek, Gemini, Kimi, GLM, Qwen, Arena, Meta AI)

OpenRender turns a normal AI chat into an agent with full control of a local project folder on your machine: it explores the code, reads and edits files, creates and deletes, searches content, runs terminal commands (installs, builds, tests, git) and reports back - all from a normal chat. No API key required.

It's a Chrome/Edge browser extension plus a small local bridge that connects the chat to the selected folder through an MCP server. **DeepSeek is the recommended provider.** Gemini, Kimi, GLM, Qwen, Arena and Meta AI also work but can be less stable: Gemini tends to stop using the commands in long sessions, and Kimi sometimes reaches for its own native tools instead. On Arena, keep the mode dropdown on **Direct**.

## Setup

**Load the extension manually (Edge or Chrome):**
1. Go to `edge://extensions` (Edge) or `chrome://extensions` (Chrome)
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `openrender-extension` folder
5. The extension is now active

**Then run the Bridge:**
1. Double-click `start.bat` (Windows) or `MacOS_Start.command` (macOS/Linux)
2. A folder picker opens: select the **project folder** the AI will control (the choice is remembered in `config.json`)
3. Keep the bridge window open
4. Go to https://chat.deepseek.com (recommended), https://gemini.google.com, https://www.kimi.com, https://chat.z.ai, https://chat.qwen.ai, https://arena.ai, or https://www.meta.ai and open a new chat
5. Click **Start agent** in the OpenRender panel and type what you want

## What the AI can do (workspace commands)

- Explore: `workspace_info`, `tree`, `list_directory`, `search_files`, `grep_files`
- Read/write: `read_file` (numbered lines), `write_file`, `edit_file` (exact-match replace)
- Organize: `create_folder`, `move_path`, `delete_path`
- Execute: `run_command` (terminal inside the folder: installs, builds, tests, git)

All paths stay inside the chosen folder; escapes outside it are refused.

## Architecture (for contributors)

The extension is split between a provider-agnostic core and per-AI-site providers:

```
core/config.js        system prompt, feedback strings, tool categories (global ZS)
core/parser.js        command parsing - pure string logic                  (global ZSParse)
core/main.js          agentic loop, UI, camouflage, session state          (uses ZSProvider)
providers/deepseek.js everything DeepSeek-specific: DOM selectors, generation
                      detection, send mechanics, composer modes…           (global ZSProvider)
providers/gemini.js   same interface for Google Gemini                     (global ZSProvider)
providers/kimi.js     same interface for Kimi / Moonshot AI                (global ZSProvider)
providers/glm.js      same interface for GLM / Z.ai                        (global ZSProvider)
providers/qwen.js     same interface for Qwen / chat.qwen.ai               (global ZSProvider)
providers/qwen-net.js MAIN-world fetch tap for Qwen SSE stream             (injected by manifest)
providers/arena.js    same interface for Arena / arena.ai                  (global ZSProvider)
providers/meta.js     same interface for Meta AI / meta.ai                 (global ZSProvider)
background.js         WebSocket to the local bridge (provider-agnostic)
```

Bridge side (project root):

```
bridge.py         WebSocket server (ws://127.0.0.1:17613); spawns MCP servers from
                  config.json as stdio children, aggregates their tools, routes calls
workspace_mcp.py  the primary MCP server: full-control file/terminal tools over one folder
config.json       server declarations + saved workspaceFolder
```

`core/main.js` never touches the host site's DOM directly - it only calls the
`ZSProvider` interface. To integrate another AI site: write a new
`providers/<site>.js` exporting the same interface, then add its URL pattern to
`manifest.json` (`content_scripts` + `host_permissions`) and to
`PROVIDER_URLS` in `background.js`. No core change required.

Run `node test-parser.js` to smoke-test the command parser.

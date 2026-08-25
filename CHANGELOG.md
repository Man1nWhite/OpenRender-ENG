# Changelog

## 0.0.1 beta

First release of OpenRender.

### Changed

- **No more Roblox Studio: the AI now controls a local project folder.** The bridge
  spawns `workspace_mcp.py`, a new primary MCP server that gives the AI full control
  over one folder chosen at startup (native folder picker on first launch, remembered
  in `config.json`).
- New workspace commands: `workspace_info`, `tree`, `list_directory`, `read_file`,
  `write_file`, `edit_file`, `create_folder`, `delete_path`, `move_path`,
  `search_files`, `grep_files` and `run_command` (terminal inside the folder:
  installs, builds, tests, git).
- Everything is sandboxed to the chosen folder; escapes outside it are refused and
  the root can never be deleted or moved.
- Renamed everywhere to **OpenRender**; version reset to 0.0.1 beta.

### Removed

- All Roblox Studio support (`launch_studio_mcp.py`, Studio probes/watchdogs,
  Luau tooling) and the Roblox-specific system prompt.
- "Free Support" and "Support with Robux / Ko-fi" sections (Ko-fi, work.ink,
  GitHub-star and Robux tip passes) from the extension panel and popup.

### Added

- **Windows distribution**: `build.py` packages the bridge into a standalone
  `OpenRender.exe` (Python and all dependencies bundled, no install needed for
  users) and assembles a portable zip with the extension included.
  `build_installer.bat` + Inno Setup produce `OpenRender-Setup-*.exe`: per-user
  installer (no admin) with Start Menu/desktop shortcuts; `config.json` survives
  reinstalls and uninstalls. The packaged exe embeds the workspace MCP server and
  re-spawns itself in worker mode (`--workspace-worker`).

### Fixed

- Editing files with CRLF (Windows) line endings no longer corrupts them with
  doubled newlines; multi-line edits match regardless of the file's line-ending
  style, which is preserved on save.

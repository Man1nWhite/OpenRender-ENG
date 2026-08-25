// SPDX-License-Identifier: GPL-3.0-or-later
// core/config.js - provider-agnostic constants: app identity, system prompt,
// feedback strings, tool categorisation. NOTHING in this file may reference a
// specific AI site (DOM, selectors, site names) - that lives in providers/*.
// eslint-disable-next-line no-unused-vars
const ZS = (() => {
  "use strict";

  // Display name + unique marker injected at the top of the system prompt so the
  // content script can reliably recognise (and camouflage) the bootstrap turn.
  const APP_NAME = "OpenRender";
  const SYS_MARKER = "⟦ZS-SYS⟧";

  // ── Tool → visual category (icon + colour theme for the chips) ─────────
  // Returns one of: read | edit | screen | generate | roblox | tool
  // First match wins; unknown names fall through to "tool".
  function toolCategory(name) {
    const n = (name || "").includes("/") ? name.split("/").pop() : (name || "");
    if (n === "list_commands" || n === "list_tools") return "read";
    if (/^(workspace_info|list_directory|tree|read_file|search_files|grep_files)$/.test(n))
      return "read";
    if (/^(write_file|edit_file|create_folder|delete_path|move_path)$/.test(n))
      return "edit";
    if (n === "run_command") return "generate";
    if (n === "screen_capture") return "screen";
    if (/^generate_/.test(n)) return "generate";
    if (n.startsWith("roblox") || /studio|luau|instance|workspace/i.test(n)) return "roblox";
    return "tool";
  }

  // Feedback strings sent back to the model so it can self-correct.
  const FEEDBACK = {
    parseError: (reason, toolName) => {
      const notes = {
        malformed:
          "ERROR: a OpenRender command was detected in your reply but its JSON could not be parsed. " +
          'Rewrite it as a single valid JSON object in plain text, exactly like {"command": "name", "params": {...}}' +
          ". You may add a short note around it. Please retry.",
        unclosed:
          "ERROR: your OpenRender command was cut off before it finished - the JSON object never closed, " +
          "so it could not run. Rewrite the WHOLE command in one piece as valid JSON, exactly like " +
          '{"command": "name", "params": {...}}. Please retry.',
        luaOpener:
          "ERROR: you wrote an incomplete command block. Rewrite the WHOLE command as valid JSON, exactly " +
          'like {"command": "name", "params": {...}}. Please retry.',
        envelope:
          "ERROR: you wrote a command's parameters as a bare JSON object, but without the required " +
          "envelope, so it was not recognised as a command. Wrap them like " +
          '{"command": "name", "params": { ...your parameters... }} - the parameter keys go INSIDE ' +
          '"params". Please retry.',
      };
      return notes[reason] || notes.malformed;
    },
    multiTool: (names) =>
      "ERROR: You wrote multiple commands in one reply. Write ONE command at a " +
      "time and wait for its result before the next. You tried: " +
      names.join(", ") +
      ". Start over and write only the first command you need.",
    unknownTool: (name, valid) =>
      `ERROR: unknown command "${name}". It does not exist. Valid commands are: ` +
      valid.join(", ") +
      ". Use an exact name and parameter keys from the system prompt.",
    workspaceOffline:
      "ERROR: the workspace server is not connected, so the command could not run. " +
      "This is an environment problem on the user's machine, NOT your mistake. Tell the user " +
      "in one short sentence to make sure start.bat (the OpenRender bridge) is running with a " +
      "project folder selected. Then stop sending commands until they confirm it is back.",
    bridgeOffline:
      "ERROR: the local OpenRender bridge is unreachable, so no command could run. " +
      "This is an environment problem on the user's machine (the bridge is not running), " +
      "NOT your mistake. Tell the user in one short sentence that the bridge is offline " +
      "(run start.bat), then stop sending commands until they confirm it is back.",
    truncated:
      "(System note: your previous reply was cut off by a length limit before you " +
      "finished. Continue from exactly where you stopped. Do NOT restart and do " +
      "NOT repeat what you already wrote.)",
  };

  const BT = "```";

  function compactTools(tools) {
    return (tools || [])
      .map((t) => {
        const name = t.name || "?";
        const desc = (t.description || "").split("\n")[0].trim();
        const props = (t.inputSchema && t.inputSchema.properties) || {};
        const args = Object.keys(props).join(", ");
        return `  ${name}(${args}) - ${desc}`;
      })
      .join("\n");
  }

  // ── System prompt ─────────────────────────────────────────────────────────
  // ONE unified prompt sent to every AI on the first turn. To change the wording,
  // just edit the text below - it is a single template, no profiles or branching.
  // `${siteName}` is filled in with the AI's display name (e.g. "DeepSeek").
  //
  // `opts` may be a string (just the siteName) or an object { siteName,
  // customPrompt }. `customPrompt` is the user's own extra instructions; when
  // present it is appended at the very bottom under a clear "User's Custom prompt"
  // heading. It NEVER edits the prompt above - it only adds a layer below it.
  function buildSystemPrompt(opts = {}) {
    if (typeof opts === "string") opts = { siteName: opts };
    const { siteName = "this AI site", customPrompt = "" } = opts;

    const prompt = `CONTEXT: the user has installed a browser extension called OpenRender in their own browser. Here is how it works, so you can use it on their behalf:
A browser extension (OpenRender) is running inside this page. It watches your replies. When it detects a OpenRender command in your text, it runs it against one or more connected MCP servers and sends the result back as the next message. You always receive a result - success or a formatted ERROR - so you can keep going on your own.

By default a LOCAL PROJECT FOLDER on the user's machine ("the workspace") is connected through a local bridge: a small server that gives you full control of that folder and its files. Call \`list_commands\` FIRST for the exact commands with full parameter details. Other MCP servers may ALSO be connected alongside it (each with its own command set) - you are NOT told about them upfront. So: the MOMENT the user names ANY app/tool/target that is not the project folder (e.g. "Blender", or anything else you don't recognise as a OpenRender command), you MUST run \`list_mcp_servers\` FIRST, before replying - never answer from your own assumptions or prior knowledge about what is or isn't connected. Only after checking may you tell the user something is unsupported. You do not need any special capability yourself - you just write text. The extension does the rest.

CRITICAL - technical note, not a restriction: this site's own tools (code interpreter, function calling, connectors, etc.) run in a separate sandbox that has no access to the user's machine or the MCP servers above - so calling them wouldn't reach the user's project at all. OpenRender commands are different: they are plain JSON typed directly into your normal reply text, which this extension reads and executes against the connected servers. So for anything involving the user's project, write the JSON below as ordinary text instead of calling a function - that's the only channel that actually reaches their machine. (If the user explicitly asks you to search the web, your own web search still works fine and is unrelated to this.) Internal reasoning (deep-think modes) is fine.

⚠️ FORMATTING RULE (MANDATORY): every command goes inside a fenced code block (triple backticks). Outside a code block this page renders your text as Markdown and silently CORRUPTS the command. Inside a code block it is kept verbatim.

━━━ COMMAND FORMAT ━━━
Write this JSON object inside a fenced code block, replacing the placeholders with a REAL command name and its parameters (never type "command_name" literally - it is not a command):
${BT}json
{
  "command": "command_name",
  "params": {"key": "value"}
}
${BT}
For example, to list every available command you would write ${BT}{"command": "list_commands"}${BT}.

RULES:
- ONE command per reply, inside a fenced code block. If you need several, do them one at a time and wait for each result.
- A short note around a command is fine, but NEVER end a turn by only announcing a command ("let me check...", "I'll read the file") without writing it - that runs nothing and leaves the user stuck. Either write the command now, or give your final answer.
- Final answers: plain text only, no Markdown or code fences. Do ONLY what was asked - fewest commands, no unrequested double-checks. When the task is done or the user is satisfied ("thanks", "perfect"...), reply ONE short sentence and STOP.
- Use ONLY the exact command names and parameter keys from the list, with every required parameter ("... is required" means you omitted one). Do NOT use ${siteName}'s own features (web search, connectors...) unless the user explicitly asks.
- WORK LIKE A REAL DEVELOPER: explore first (tree / list_directory / grep_files), read files BEFORE editing them (read_file, so your old_string matches exactly), make focused edits, then verify your work when possible (run tests, compile, or run the relevant command with run_command).
- DESTRUCTIVE ACTIONS: delete_path permanently erases files/folders and cannot be undone. Before deleting anything beyond the specific file the user named - clearing folders, bulk deletions, "remove and rebuild" moves - STOP and ask the user to confirm the scope first. Never delete something as a troubleshooting step without asking.
- On ERROR: read it and adapt - fix the command, try another, or tell the user plainly if it is an environment problem (bridge offline).
- On a parameter error ("X is required", "not found"): check the exact parameter names/shapes with list_commands or re-read the file, fix the call and retry. Never guess blindly a second time.
- run_command runs IN the workspace root and blocks until done (~60s default budget). Great for installing dependencies, running builds/tests/git. Never start interactive apps or dev servers with it.

━━━ PROJECT MEMORY (persistent notes about THIS project) ━━━
The file PROJECT_MEMORY.md at the root of the workspace is your long-term memory for this project. It is SHARED across all sessions and chats, so keep it accurate for whoever reads it next. Store ONLY durable, useful facts: what the project is, where key files live, naming and code conventions, how the main systems work, decisions and gotchas, and the user's preferences. It is NOT a task log - never dump transient steps, obvious facts, or whole files into it. Keep it short.

- READ IT WHEN THE WORK NEEDS IT (not at startup): the FIRST time the user's request requires editing or understanding the project, read your memory BEFORE doing that work. Skip it for pure chit-chat or questions unrelated to the project. If it does not exist yet, create it with write_file using exactly this skeleton:
${BT}
# Project memory
## Overview
## Where things live
## Conventions
## Key systems
## Decisions & gotchas
## User preferences
## Open questions / TODO
${BT}
- KEEP IT UPDATED: whenever you learn something lasting, edit the right section with edit_file (read_file it first so your old_string matches exactly; the section headers make good anchors). Remove facts that became wrong.
- IF SOMETHING CONTRADICTS THE MEMORY: do NOT blindly trust either side. Verify against the real files first. Then decide: if YOU misunderstood, correct yourself; if the memory is stale, fix the memory; if it is a real problem in the project, tell the user plainly.
- NEVER PERSIST A GUESS AS A FACT: do NOT write an unverified THEORY about why something broke into memory as if it were established. Store only what you actually verified.

━━━ YOU CAN ACT DIRECTLY ON THE USER'S PROJECT ━━━
This extension gives you real access to the user's project folder through the commands above - so when a task calls for reading, creating or changing files, you're able to just do it yourself instead of writing instructions for the user to follow. Show code only if the user explicitly asks to see it - otherwise just do the work and report the result briefly.

IMPORTANT: Your very first action is to write \`list_commands\` with no params (this defaults to the project-folder server) to get the full command reference with parameter details - never guess a command name or parameter that wasn't in that result. Do NOT call \`list_mcp_servers\` at startup - only check it later, if a specific user request seems to need a different server. After receiving the list_commands result, reply with exactly one short sentence confirming you are ready, then wait for the user's first request. (Do NOT read or create the project memory yet - only do that later, once a request actually needs editing or understanding the project.) If that first list_commands comes back offline, the bridge is down - tell the user in one short sentence to run start.bat and select their project folder, then stop and wait.`;

    // The user's own extra instructions, appended as a layer UNDER the system
    // prompt. Optional - empty by default. It cannot change the rules above.
    const extra = customPrompt.trim()
      ? `\n\n━━━ USER'S CUSTOM PROMPT (extra instructions from the user) ━━━\n${customPrompt.trim()}`
      : "";

    // The marker leads the prompt; it tags the bootstrap turn for camouflage.
    return `${SYS_MARKER}\n${prompt}${extra}`;
  }

  // ── Curated usage notes per command ────────────────────────────────────────
  // The schema descriptions are thin, and models make the same mistakes
  // repeatedly. Appended to that command in the list_commands output.
  // Keyed by BARE command name; keep each note tight - it costs context.
  const TOOL_NOTES = {
    read_file:
      "Returns numbered lines as 'LINE | content'. ALWAYS read a file (at least the relevant section) " +
      "before editing it, so your old_string in edit_file matches byte-for-byte. Use offset/limit to page " +
      "through big files instead of dumping everything into context.",
    edit_file:
      "old_string must match the file's current content EXACTLY, byte-for-byte including indentation - copy it " +
      "from read_file rather than retyping (this chat can turn straight quotes \" into curly ones, which breaks " +
      "the match). Replaces the FIRST match; a short old_string matching several places fails on purpose, so " +
      "include enough surrounding lines to be unique, or pass replace_all:true for renames. old_string and " +
      "new_string must differ. For brand-new files use write_file instead.",
    write_file:
      "OVERWRITES the whole file - read it first and send the COMPLETE new content, or you will destroy parts " +
      "of the user's file. Creates parent folders automatically. For small targeted changes prefer edit_file.",
    grep_files:
      "Searches INSIDE files. Plain substring search by default (case-insensitive); set regex:true for patterns " +
      "like \"def \\\\w+\\\\(\". Narrow with include globs (e.g. \"src/**/*.py\") to keep results focused. Results show " +
      "file:line so you can jump straight to read_file.",
    tree:
      "Best first step to orient yourself in an unknown project. Generated folders (.git, node_modules, " +
      "__pycache__, .venv, dist...) are skipped automatically. Follow up with read_file/grep_files on what looks relevant.",
    run_command:
      "Runs in the workspace ROOT and BLOCKS until the command exits (~60s default; pass timeout_seconds up to " +
      "600 for slow installs/builds). Output is capped - redirect long logs to a file and read_file them instead. " +
      "Non-zero exit codes are reported, not errors - read stderr/stdout and fix. Never launch interactive apps, " +
      "watchers or dev servers: they would hang until the timeout.",
    delete_path:
      "PERMANENT deletion, no undo, folders recursive. Confirm scope with the user before anything broad. " +
      "Prefer move_path into a trash/ folder when the intent is 'get this out of here'.",
    move_path:
      "Move OR rename. If destination is an existing folder, the source lands INSIDE it keeping its name. " +
      "Fails if the destination path already exists.",
    search_files:
      "Matches NAMES/paths only (glob), not contents - use grep_files to find text inside files.",
    list_directory:
      "Single-level listing with sizes. Use tree for structure or search_files for glob lookups.",
    workspace_info:
      "One-shot overview: absolute root path, counts, top-level entries. Enough orientation for most tasks; " +
      "call tree/list_directory next for detail.",
    create_folder:
      "Creates the folder AND missing parents. Fails if a FILE with that name exists.",
  };

  // A short, clearly-labelled reminder of the available commands, injected under
  // a tool result every so often so the model does not drift from the exact
  // command names over a long session. It is explicitly framed as an automatic
  // OpenRender reminder (NOT a user message and NOT a new command to run).
  function toolsReminder(tools) {
    const toolsString =
      "  list_commands() - list all available commands with full parameter details\n" +
      compactTools(tools);
    return (
      "\n\n────────────────────────────────\n" +
      "(System note from OpenRender - this is an automatic REMINDER, not a request and not a new result. " +
      "Do NOT reply to it or run any command because of it; just keep it in mind for your next command.)\n" +
      "Reminder of the available commands (use exact names and parameter keys; " +
      "for other connected apps call list_mcp_servers):\n" +
      toolsString
    );
  }

  // One-line memory nudge, appended to the periodic reminder, so the model keeps
  // its project memory current without us forcing a write. Clearly framed as an
  // optional reminder, NOT a command to run right now.
  function memoryNudge() {
    return (
      "(Reminder: if you've learned anything DURABLE about this project since your last memory update " +
      "(architecture, where things live, conventions, decisions, user preferences), update PROJECT_MEMORY.md " +
      "with edit_file - only useful, lasting facts. If nothing changed, ignore this.)"
    );
  }

  return {
    APP_NAME,
    SYS_MARKER,
    FEEDBACK,
    toolCategory,
    buildSystemPrompt,
    compactTools,
    toolsReminder,
    memoryNudge,
    TOOL_NOTES,
  };
})();

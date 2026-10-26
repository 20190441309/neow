# Neow Web Studio: Conversation First

## Direction

The current iteration deliberately replaces the earlier Awwwards-inspired
editorial layout. The requested reference is
[dsh-web](https://github.com/zhu1090093659/dsh-web), specifically its official
`docs/screenshots/13-hero-main.png`: a narrow navigation rail, a spacious
conversation canvas, and a centered bottom composer. Cool neutrals, fine
borders, compact labels, and a restrained blue accent support that structure.

This borrows the reference's information hierarchy, not its wallpaper, desktop
pet, plugin ecosystem, or unavailable session-history features. Large slogans,
the orbital illustration, numbered starter cards, branding badges, and the
permanent inspector have been removed. The Neow monogram and icons remain
repo-native SVG/CSS. Self-hosted Space Grotesk and IBM Plex Mono retain their
licenses in `neow/web/static/FONT-LICENSES.txt`.

## Layout and behavior

- Left: new conversation, current conversation, and a collapsed project-resource
  browser. Files and skills appear only when requested; the composer `@` control
  opens files directly. The bottom project button always opens the switcher.
- Project files form a native disclosure tree, with folders first and direct
  children loaded only on expansion. Each directory pages independently, so
  large projects remain browsable beyond 200 files. Search groups matches under
  expanded parent folders and preserves normal expansion choices when cleared.
  File actions display basenames but retain full relative paths for previews
  and `@` references. Switching projects clears the tree and pending responses.
- Center: a short empty-state prompt, three small editable suggestions, the
  conversation timeline, and a persistent composer capped at 800px content width.
- Low-frequency planning, autonomous-task, diff, and compaction actions live in
  the bottom "More" disclosure. Approval and thinking settings are grouped in a
  composer disclosure. Menus close on outside click, selection, or Escape;
  keyboard focus returns to a visible summary rather than a hidden action.
- Task progress, autonomous goals, background processes, usage, and Git state
  live in an opt-in right drawer at every viewport size. Below 760px the left
  navigation is also a drawer. Focus is trapped in an open drawer or dialog,
  and obscured content is inert. Resource tabs use a roving keyboard tab stop.
- The busy composer swaps send for stop instead of displaying both controls.
- Light and dark themes use the same cool-neutral hierarchy and persist locally.
  Motion is limited to brief reveals with reduced-motion support.
- Existing model configuration formats remain compatible. The UI does not display
  saved API keys, and browsing starter suggestions does not initiate model calls.

## Workspace switching

- The workspace picker accepts an existing, readable absolute directory path,
  or a directory selected through the local browser. It does not create folders.
  Listings are bounded to 500 directories; recent workspaces last for the current
  server process. All browser tabs connected to that server share one workspace.
- Switching starts a fresh conversation in the same server process. Before
  clearing the previous project state, nonempty conversation, plan, and context
  data are archived to `~/.neow/sessions/web_*.json`. An archive failure prevents
  the switch. Existing project files and previous checkpoint backups are not
  reverted or deleted by the switch.
- The new workspace reloads project instructions, file context, Git information,
  and available skills. Conversation state, enabled skills, pending plans, goals,
  command working-directory overrides, read-before-edit tracking, and session
  approval grants are reset; new file checkpoints are used for the new project.
- The selected model and launch configuration are retained. The destination's
  `.neow.json`, hooks, and MCP servers are not automatically activated. Model
  configuration changes continue to save to the original configuration file,
  not into the newly selected project.
- Token usage, cost, and token-limit accounting remain cumulative for the running
  process. Neither clearing the conversation nor switching workspaces resets
  the usage budget. A fresh conversation is not a fresh process or budget.
- A switch is refused while a conversation or management operation, autonomous
  goal, pending interaction, or background task is active. Project-owned launch
  configurations, configured shell hooks, custom plugins, and live project-scoped
  or stdio MCP connections also require restarting Neow in the target directory.
  User-owned HTTP MCP connections and terminal inactive connections do not block
  switching; the destination's integrations still require explicit setup.
- Stopping a Web turn retains its busy reservation until cancelled tool and
  sub-agent workers actually exit. Slow external work can delay that release;
  the UI must not offer a safe project switch while old workers still run.
- Browser mutations carry the workspace generation. A stale tab receives a
  conflict instead of executing its old-project request in the new workspace;
  mutations are never silently retried after a switch.

## Local security boundaries

The server is a local single-user workbench, not a hosted multi-user service.
Requests must target its loopback host and exact port; browser cross-origin and
cross-site requests are rejected, and API responses do not expose wildcard CORS.
JSON is required for mutations. These checks do not authenticate other local
programs, so do not expose the server through a public proxy.

File previews and `@file` references are constrained to the resolved workspace,
including symlink traversal checks. References support quoted paths containing
spaces, reject non-text or oversized files, and are validated before a turn is
accepted. These UI restrictions are not a general agent sandbox: the existing
tool approval policy and command-security settings still govern agent actions.
Session archives are local plaintext and can contain shared source files and
conversation content; treat the user's `.neow` directory as private data.

## Verification

```powershell
node --check neow/web/static/app.js
node --test tests/web_frontend.test.cjs
.\.venv\Scripts\python.exe -m pytest tests/test_web_frontend.py tests/test_web_server.py tests/test_web_workspaces.py --no-cov -q
```

The frontend tests use Node's built-in test runner, a lightweight DOM fixture,
and Python's standard HTML parser. No browser automation package is required.
They cover DOM contracts, accessible control names, dialog semantics, on-demand
tools, desktop/mobile drawer behavior, resource navigation, menu focus,
send/stop visibility, escaped output, draft preservation, IME submission,
clear recovery, and reconnect helpers.
Backend tests additionally cover workspace validation and switching, runtime
integration guards, local request-origin checks, file-reference boundaries,
directory pagination and traversal boundaries, real approval/question callbacks,
and cumulative usage reporting. Directory-tree frontend tests cover lazy loads,
retry behavior, stale responses, search hierarchy, and retained expansion state.

Visual QA covers desktop, tablet, and mobile breakpoints, both themes, model
configuration, file search and references, plan dialogs, and responsive panels.
Streaming and long-message layout are exercised against an isolated fake
conversation, without invoking a paid model or modifying project files.

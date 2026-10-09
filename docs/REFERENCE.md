# AgentLTL for Codex: full reference

The plugin is the [Claude Code plugin](https://github.com/AgentLTL/agentltl-claude-code)'s
guard on OpenAI Codex CLI's hooks. Both are thin layers over
[agentltl-coding](https://github.com/AgentLTL/agentltl-coding), which holds the rule language,
the library, the guard and what the hooks do; each plugin only translates its agent's
payloads, tool names and files.

## Setup

```bash
codex plugin marketplace add AgentLTL/agentltl-codex
codex plugin add agentltl@agentltl
"$(ls -td ~/.codex/plugins/cache/agentltl/agentltl/*/ | head -1)"bin/agentltl install
```

- Codex copies each plugin version into
  `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/` and runs the hooks of its
  `hooks/hooks.json`, but only once each is trusted: until then it skips them without a word,
  plugin hooks or not, in `codex exec` too. `agentltl install` trusts AgentLTL's hooks by
  writing their hashes in `~/.codex/config.toml`, between two marker comments, and leaves the
  rest of the file alone:

  ```toml
  [hooks.state."agentltl@agentltl:hooks/hooks.json:pre_tool_use:0:0"]
  trusted_hash = "sha256:…"
  ```

  You can approve each hook in Codex's `/hooks` instead. `agentltl uninstall` removes the
  entries (the plugin and the rule files stay). A plugin update that changes a hook's
  definition changes its hash: Codex's `/hooks` then says "review required", and the hook
  doesn't run until `agentltl install` is run again.
- `agentltl install` also puts a small `agentltl` command in `~/.local/bin` that runs the
  newest installed version.
- The first hook builds a Python environment in
  `~/.codex/plugins/data/agentltl-agentltl/venv-<pins>` (`$PLUGIN_DATA`; `$CODEX_HOME` moves
  `~/.codex`), from the commits pinned in `vendor.lock`. It needs Python 3.10+ and git. An
  update that changes the pins builds a new one; environments unused for 14 days are removed.
- Rules apply where an `AGENTLTL.yaml` is: the project's (found from the working directory up
  to the git root) and the user's, `~/.codex/AGENTLTL.yaml`. Without either, the hooks exit at
  once.
- **Updating:** `agentltl update` runs
  `codex plugin marketplace upgrade agentltl && codex plugin add agentltl@agentltl`, then
  `install` again with the new version.
- **From a git checkout** (development):

  ```bash
  git clone --recurse-submodules https://github.com/AgentLTL/agentltl-codex.git
  codex plugin marketplace add ./agentltl-codex
  codex plugin add agentltl@agentltl
  "$(ls -td ~/.codex/plugins/cache/agentltl/agentltl/*/ | head -1)"bin/agentltl install
  ```

## Claude Code plugin features, in Codex

| Claude Code plugin | Codex plugin |
|---|---|
| `claude plugin install agentltl@agentltl` | `codex plugin marketplace add AgentLTL/agentltl-codex`, `codex plugin add agentltl@agentltl`, then `agentltl install` to trust the hooks |
| Hooks in the plugin's `hooks.json` | the same file and events, run once trusted (`agentltl install`, or `/hooks`) |
| `SessionStart`: the rules in force | the same (`additionalContext`, and `systemMessage` "AgentLTL: N rule(s) in force"); `SubagentStart` lists them to a subagent |
| `UserPromptSubmit`: lifts a `stop`, starts a turn | the same; it also marks pending `ask`s answered. A subagent's task prompt (with an `agent_id`) is not the user and is ignored |
| PreToolUse `deny`, with a reason | the same; Codex gives the model "Command blocked by PreToolUse hook: <reason>". Notes from `log` and `warn` rules go as `additionalContext` |
| PreToolUse `ask` | no such answer (Codex would treat it as a hook failure and allow the call): the call is denied, Codex is told to ask the user in its reply and end its turn (or use `request_user_input` in Plan mode), and once the user writes again the exact same call goes through once |
| `systemMessage` | the same: shown to the user as a notice (rules in force, refusals, credential warnings, `finally` send-backs); `codex exec --json` doesn't show them |
| PostToolUse / PostToolUseFailure | PostToolUse, for successful and failed commands: status 1 when the command's exit code, read from the session's rollout file (`transcript_path`), is non-zero. A failed `apply_patch` has none: nothing ran |
| Stop `decision: block` for `finally` rules | the same: Codex gets the reason as a user message (`<hook_prompt>`) and goes on, at most `finish_retries` times per turn |
| `permission_mode` (auto modes) | `bypassPermissions` (approval policy `never`: `--yolo`, and `codex exec` always), or `AGENTLTL_AUTO=1`: `ask` is refused, `unparseable.auto` applies. `AGENTLTL_AUTO=0` says someone is there anyway (an interactive `--yolo` session, or a script that answers with `codex exec resume`) |
| `CLAUDE_PROJECT_DIR` | `CODEX_PROJECT_DIR`, else the git root of the working directory |
| Tools `Bash`, `Write`, `Edit`, `Read`, `Task`, `WebSearch` | the shell tool (`exec_command`) reaches hooks as `Bash {command}`; `apply_patch` is checked and recorded as the `Write` / `Edit` / `rm` calls it stands for; no Read tool: the files a successful `cat`, `head`, `tail`, `sed` (not `-i`), `nl`, `less`, `more`, `bat` or `tac` printed count as `Read`; `view_image` is `Read`, `spawn_agent` is `Task`, `web_search` is `WebSearch`; MCP tools are `mcp__<server>__<tool>` |
| Subagents (`Task`) | `spawn_agent`, recorded as `Task`; Codex runs hooks inside subagents, and their calls are checked and recorded in the parent's session (the same `session_id`). A subagent's end doesn't trigger `finally` |
| `~/.claude/AGENTLTL.yaml` | `~/.codex/AGENTLTL.yaml` |
| Memory: `CLAUDE.md`, `.claude/rules/`, auto memory | Instructions: `AGENTS.override.md` or `AGENTS.md` in each folder from the project root down to the working directory (and the config's `project_doc_fallback_filenames`); `~/.codex/AGENTS.override.md` or `~/.codex/AGENTS.md` |
| Built-in rule `memory-first` | the same, on writes to `AGENTS.md` and `AGENTS.override.md` |
| Skills `/agentltl:setup`, `:rules`, `:import`, `:status` | `$agentltl:setup`, `$agentltl:rules`, `$agentltl:import`, `$agentltl:status` (or pick them in `/skills`) |
| Status line | Codex's status line takes fixed items only: `$agentltl:status` and `agentltl trace` |
| Library `no-claude-coauthor`, `subagents-on-sonnet` | `no-codex-coauthor` (Codex's `Co-authored-by: Codex <noreply@openai.com>`, and "Generated with Codex" in pull requests, when commit attribution is on); the Claude Code entries switch nothing on here |

## Hooks

| Event | Input used | Answer |
|---|---|---|
| `SessionStart` | `session_id`, `cwd` | `additionalContext`: the rules in force; `systemMessage` for the user |
| `SubagentStart` | `session_id`, `cwd` | `additionalContext`: the rules, for the subagent |
| `UserPromptSubmit` | `session_id`, `agent_id` | nothing: lifts a `stop`, resets `finally` send-backs, marks pending `ask`s answered |
| `PreToolUse` | `tool_name`, `tool_input`, `permission_mode` | `permissionDecision: deny` with a reason, and `systemMessage`; `additionalContext` for a rule's note; nothing when there is no objection |
| `PostToolUse` | `tool_use_id`, `tool_response`, `transcript_path` | `additionalContext` and `systemMessage` when the output holds a credential, or a rule left a note |
| `Stop` | `session_id` | `decision: block` with what a `finally` rule still needs |

Codex lets a call through when a hook fails (an exit status other than 0 or 2, invalid JSON,
a timeout). So `hooks/run` always exits 0, and answers a `PreToolUse` it could not check (a
guard error, a Python crash, an environment it could not build) with a denial. A hook that
Codex kills on its timeout (120 s for `PreToolUse`) still lets the call through. The guard
never answers `allow`: silence leaves the call to Codex's own approvals and sandbox.

## Modes

| Mode | In Codex |
|---|---|
| `block` | denied with the reason |
| `warn` | denied once; Codex may repeat the exact same call to go ahead |
| `ask` | denied; Codex asks you in its reply and ends its turn (in Plan mode, `request_user_input`); once you write again, the exact same call goes through once. Refused in unattended runs |
| `retry` | denied; after `retries` attempts, as `ask` |
| `stop` | denied, and every call is denied until you write again |
| `log` | allowed; Codex gets the note before the call runs |

## Rules

The rule language is the same in every harness: see the
[rules reference](https://agentltl.github.io/rules/reference/) and the
[library](https://agentltl.github.io/rules/library/). In `agentltl check`, name the calls an
`apply_patch` stands for: `'Write {"file_path": ".env", "content": "x"}'`,
`'Edit {"file_path": "a.py", "old_string": "x", "new_string": "y"}'`, `"rm -- old.txt"`.

## Limitations

- **Hooks must be trusted.** Run `agentltl install` again after an update that changes
  `hooks/hooks.json`; otherwise Codex's `/hooks` shows "review required" and the hooks don't
  run.
- **A hook timeout lets the call through** (120 s for `PreToolUse`).
- **`ask` is emulated**: the call is refused and Codex asks you; the plugin lets it through
  once you have written, trusting Codex to respect a "no".
- **Reads through the shell** count only for the viewer commands above: a file printed by
  `python -c` or `awk` doesn't count as read.
- **Exit codes come from the rollout file.** If Codex stops writing it, failed commands count
  as successful.
- **Notices** (`systemMessage`) are not shown by `codex exec --json`.
- **Input sent to a running process** (`write_stdin`) is not checked.

## State

Session and project traces live in the plugin's data directory (`sessions/`, `projects/`),
as in the Claude Code plugin: `agentltl trace` shows them, `agentltl reset` forgets them.

## Development

```bash
git clone --recurse-submodules https://github.com/AgentLTL/agentltl-codex.git
scripts/setup.sh --dev && .venv/bin/python -m pytest -q
```

`docker/Dockerfile` is an image with Codex to try the plugin end to end, with a scripted model
or any OpenAI-compatible model that serves the Responses API (see the README).

# AgentLTL for Codex

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![arXiv](https://img.shields.io/badge/arXiv-2607.02599-b31b1b.svg)](https://arxiv.org/abs/2607.02599)
[![Docs](https://img.shields.io/badge/docs-agentltl.github.io-3f51b5.svg)](https://agentltl.github.io/harnesses/codex/)

> Rules Codex can't forget.

`AGENTS.md` is advice: Codex can lose it in a long session or inside a subagent. AgentLTL
checks every tool call [OpenAI Codex CLI](https://github.com/openai/codex) makes against the
rules in `AGENTLTL.yaml` **before it runs**, and refuses the ones that break them.

```
> ship 1.6.0 to prod

  ✗ shell  helm upgrade web repo/web --version 1.6.0 -n prod
    Rule 'promote-what-staging-ran' blocked this call. Nothing was executed.
    Problem: for chart='repo/web', v='1.6.0': no earlier helm_upgrade call had
             namespace='staging', chart='repo/web', version='1.6.0'.

  ✓ shell  helm upgrade web repo/web --version 1.6.0 -n staging
  ✓ shell  curl -fsS https://staging.example.com/health
  ✓ shell  helm upgrade web repo/web --version 1.6.0 -n prod
```

One rule did that:

```yaml
- id: promote-what-staging-ran
  before:
    first: {tool: helm_upgrade, with: {chart: $chart, version: $v, namespace: staging}}
    then:  {tool: helm_upgrade, with: {chart: $chart, version: $v, namespace: prod}}
  scope: project       # the staging deploy may have been yesterday, in another session
```

This is the [Claude Code plugin](https://github.com/AgentLTL/agentltl-claude-code)'s guard, on
Codex's hooks: the same rule language, the same library and the same `AGENTLTL.yaml`, so a
project can share one rule file between Codex, Claude Code and the other
[supported agents](https://agentltl.github.io/harnesses/). It works with whatever model Codex
runs, OpenAI's or your own.

## Features

- **Order-aware rules:** tests before push, plan before apply, staging before prod; per session
  or across the whole project.
- **Variables across calls:** `$variables` tie calls together by their arguments.
- **Real shell parsing:** `git commit -am x && git push -f` is checked as `git_commit` then
  `git_push{force: true}`, all or nothing.
- **Patches as edits:** an `apply_patch` is checked as the files it adds, updates and deletes,
  so rules on `Write`, `Edit` and `rm` hold for it.
- **Plain-language rules:** ask Codex to "add a rule: never push to main" (`$agentltl:rules`);
  it writes the rule and tests it before saving.
- **Opt-in rule library:** tested rules for git, secrets, installs and infrastructure
  (`$agentltl:setup`).
- **`finally` rules:** "run the tests before you finish": Codex is sent back before it ends its
  turn.
- **Secret leak alerts:** when a command's output contains what looks like a credential, Codex
  is told not to repeat it and you get a notice, so you can rotate it.
- **Rules instead of instructions:** when Codex would write a rule into `AGENTS.md`, it writes
  an enforced rule instead; `$agentltl:import` does the same for what your instructions
  already hold.
- **Fail-safe:** never approves a call; if the guard can't answer, the call is refused.

## Installation

Requires Python 3.10+, git, and OpenAI Codex CLI (tested with 0.162).

```bash
codex plugin marketplace add AgentLTL/agentltl-codex
codex plugin add agentltl@agentltl
"$(ls -td ~/.codex/plugins/cache/agentltl/agentltl/*/ | head -1)"bin/agentltl install
```

Codex runs no hook, a plugin's or your own, until you trust it. `install` trusts AgentLTL's
hooks in `~/.codex/config.toml` (between two marker comments; the rest of the file is kept),
and puts the `agentltl` command in `~/.local/bin`. You can approve each hook in Codex's
`/hooks` instead. The plugin builds its Python environment on first use (in
`~/.codex/plugins/data/`) and does nothing until there is an `AGENTLTL.yaml`: at a project's
root for that project, or in `~/.codex/` for every project. Start with `$agentltl:setup` in a
Codex session to pick rules from the library.

**Updating:** `agentltl update` (it upgrades the plugin, then trusts the new version's hooks).
**Removing:** `agentltl uninstall`, then `codex plugin remove agentltl@agentltl`.

## Usage

### Rules

```yaml
# AGENTLTL.yaml
use: [tests-before-push, no-force-push, protect-env-files, no-codex-coauthor]

rules:
  - id: tests-before-push-here
    before: {first: {tool: make, with: {argv: check}}, then: git_push, since: [Edit, Write]}
    why: CI is slow; run the checks locally first.
    mode: warn
  - id: changelog
    finally: {call: {tool: Edit, where: {file_path: CHANGELOG.md}}, since: [Edit, Write]}
    why: Every change gets a CHANGELOG line.
```

Rules name tools as the library does, with Claude Code's names, so one file serves every
agent; Codex's tools are mapped onto them:

| Codex | Rules say |
|---|---|
| shell `{command}` | the commands it runs (`git_push`, `pytest`...) |
| `apply_patch` | `Write` (Add File), `Edit` (Update File), `rm` (Delete File), with `file_path`... |
| `cat`, `head`, `sed -n`... on a file | also `Read {file_path}`: Codex has no Read tool |
| `view_image`, `spawn_agent`, `web_search` | `Read`, `Task`, `WebSearch` |

The full language (rule kinds, targets, variables, memory, modes) is in the
[rules reference](https://agentltl.github.io/rules/reference/), and the packaged rules in the
[library](https://agentltl.github.io/rules/library/). Library entries for another agent only
(`no-claude-coauthor`, `no-copilot-coauthor`, `subagents-on-sonnet`) switch nothing on in
Codex, so a shared file stays valid. With commit attribution on, Codex signs commits
(`Co-authored-by: Codex <noreply@openai.com>`) and pull requests ("Generated with Codex");
`no-codex-coauthor` refuses those commits.

### Modes

| Mode | The call is | Who can let it through |
|---|---|---|
| `block` | denied, with the reason | you |
| `warn` | denied once | Codex, by repeating the exact same call |
| `ask` | denied; Codex asks you, then the exact same call goes through once | you |
| `retry` | denied; after the allowed retries, as `ask` | you |
| `stop` | denied, and every call is refused until you reply | you |
| `log` | allowed; Codex is told it broke the rule | n/a |

### Skills and commands

| In Codex | What it does |
|---|---|
| `$agentltl:setup` | pick packaged rules to switch on |
| `$agentltl:rules` | add, change or remove a rule in plain words |
| `$agentltl:import` | turn instructions (`AGENTS.md`) into enforced rules |
| `$agentltl:status` | the rules in force and what they blocked |

Type them in a message, or pick them in `/skills`.

| Command | What it does |
|---|---|
| `agentltl install`, `uninstall`, `update` | the trust of the hooks in `~/.codex/config.toml` |
| `agentltl validate` | compile the rule files and list the rules |
| `agentltl check "git push" "pytest" "git push"` | replay steps through the rules |
| `agentltl translate "git commit -am x && git push"` | the calls a command line stands for |
| `agentltl library`, `use NAME`, `unuse NAME` | the packaged rules |
| `agentltl trace`, `reset` | what the guard recorded in this session and project |
| `agentltl memory scan` | statements in your instructions that could be rules |

## How it works

Codex runs the plugin's hooks (`hooks/hooks.json`) around every tool call:

| Hook | AgentLTL |
|---|---|
| `SessionStart`, `SubagentStart` | lists the rules in force to Codex, or to the subagent |
| `PreToolUse` | decides the call: `deny` with the reason, or silence |
| `PostToolUse` | records the call that ran (and whether it failed), scans the output for credentials |
| `UserPromptSubmit` | you replied: lifts a `stop`, lets an approved `ask` through |
| `Stop` | sends Codex back while a `finally` rule is unmet |

Codex's hooks have no "ask" answer, so the plugin emulates it; the
[full reference](docs/REFERENCE.md) says how, and maps every feature of the Claude Code plugin
onto Codex. Shell command lines are translated by
[cli-to-tools](https://github.com/AgentLTL/cli-to-tools) into the calls they run; the rules are
compiled by [agentltl-coding](https://github.com/AgentLTL/agentltl-coding) into
[AgentLTL](https://github.com/AgentLTL/AgentLTL) formulas, checked on the calls so far.

## Limitations

- **Hooks must be trusted.** Codex runs a hook only once it is trusted, and a hook whose
  definition changed needs trusting again: re-run `agentltl install` after an update that
  changes `hooks/hooks.json` (Codex's `/hooks` shows "review required" otherwise).
- **A hook timeout lets the call through.** Codex allows a call when a hook fails, so the
  plugin's hooks always answer, and refuse a call they couldn't check; but a hook that Codex
  kills on its timeout (120 s for `PreToolUse`) answers nothing, and the call goes ahead.
- **`ask` goes through Codex.** Codex's hooks can't prompt you, so an `ask` rule refuses the
  call and Codex asks you in its reply; once you have written, the exact same call goes
  through once, trusting Codex to respect a "no". When Codex's approval policy is `never`
  (`codex exec`, `--yolo`) nobody can answer, so an `ask` is refused; in an interactive
  `--yolo` session, start Codex with `AGENTLTL_AUTO=0` to be asked.
- **Reads through the shell:** only `cat`, `head`, `tail`, `sed` (not `-i`), `nl`, `less`,
  `more`, `bat` and `tac` count as reading a file; one printed by `python -c` or `awk` doesn't.
- **Exit codes come from the session's rollout file.** If Codex stops writing it, failed
  commands count as successful.
- **Notices** (`systemMessage`) are not shown by `codex exec --json`.
- **Input to a running process** (`write_stdin`) is not checked.
- The rest is as in the [Claude Code plugin](https://agentltl.github.io/harnesses/claude-code/):
  a rule sees tool calls, not what a script does inside.

## Development

```bash
git clone --recurse-submodules https://github.com/AgentLTL/agentltl-codex.git
cd agentltl-codex
scripts/setup.sh --dev
.venv/bin/python -m pytest -q
```

To try a checkout in Codex, install it from its folder:

```bash
codex plugin marketplace add ./agentltl-codex
codex plugin add agentltl@agentltl
"$(ls -td ~/.codex/plugins/cache/agentltl/agentltl/*/ | head -1)"bin/agentltl install
```

`docker/` has an image with Codex (Node 22 and Python, user `dev`, a scratch repository in
`/work`) for trying the plugin end to end:

```bash
docker/e2e.sh                   # no model needed: a scripted model makes the calls
cp .env.example .env            # your OpenAI-compatible endpoint, key and model
docker/live.sh "a task"         # one `codex exec` session on your model, with e2e/AGENTLTL.yaml
```

Codex only speaks the Responses API (`wire_api = "responses"`), so the scripted model serves
it, and your server must serve `/v1/responses` (vLLM does). The Codex version `docker/e2e.sh`
tests is pinned in `docker/package.json`; Dependabot proposes each new release as a pull
request, and the end-to-end workflow flags the ones that break the plugin.

## Documentation

[agentltl.github.io](https://agentltl.github.io/harnesses/codex/), and
[docs/REFERENCE.md](docs/REFERENCE.md) here.

## License

MIT. See [LICENSE](LICENSE).

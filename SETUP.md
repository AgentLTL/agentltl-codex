# Setting up AgentLTL for Codex

These instructions are for OpenAI Codex CLI. A user pasted a prompt asking you to set up this
plugin. Follow the steps in order. Say briefly what you are doing at each step, and stop to ask
the user only where a step says so.

The plugin checks every tool call against the rules in an `AGENTLTL.yaml` file, and refuses
calls that break them. Nothing has to be cloned. The plugin installs from GitHub into
`~/.codex/plugins/` and works in every project. The only file that lives in a project is
`AGENTLTL.yaml`, at the project root (or in `~/.codex/` to apply to every project).

## 1. Check the prerequisites

Run `python3 --version`, `git --version` and `codex --version`.

- **Python 3.10 or newer, git, and Codex CLI:** all are needed. If one is missing or too old,
  stop and tell the user what to install. On macOS that is `brew install python git`; on Debian
  or Ubuntu, `sudo apt install python3 python3-venv git`.
- **`python3 -m venv`:** run `python3 -m venv --help > /dev/null`. On Debian and Ubuntu it can
  be missing even when Python is installed; the fix is `sudo apt install python3-venv`.

## 2. Look for an earlier setup

Check whether `ls -d ~/.codex/plugins/cache/agentltl/agentltl/*/` finds a folder. If it does,
the plugin is already installed: skip to step 4.

## 3. Install the plugin

```bash
codex plugin marketplace add AgentLTL/agentltl-codex
codex plugin add agentltl@agentltl
```

If the first command says the marketplace already exists, continue with the second.

## 4. Build the environment and trust the hooks

Codex runs no hook, a plugin's or the user's own, until it is trusted. The plugin's `install`
command builds its Python environment (10 to 30 seconds), trusts AgentLTL's hooks in
`~/.codex/config.toml` (between two marker comments; the rest of the file is kept), and puts the
`agentltl` command in `~/.local/bin`:

```bash
plugin=$(ls -td ~/.codex/plugins/cache/agentltl/agentltl/*/ | head -1)
"${plugin}bin/agentltl" install
```

Tell the user that this edits `~/.codex/config.toml`; the alternative is for them to approve each
hook in Codex's `/hooks`. Check that `~/.local/bin` is on the PATH; if it is not, write
`"${plugin}bin/agentltl"` wherever the steps below say `agentltl`.

## 5. Choose the first rules, with the user

The plugin ships a library of tested rules the user can switch on by name. Start there:
read `${plugin}skills/setup/SKILL.md` and follow it. Run the commands from the project root.

Then ask whether there is anything else Codex should never do, or always do first, in this
project. For each answer, write a rule following `${plugin}skills/rules/SKILL.md`. In short:

- **Tool names:** rules use the names commands translate to. Check with
  `agentltl translate "git push --force"`.
- **Explain each rule:** give every rule a `why` (Codex sees it when blocked) and a `mode`
  matching how strict the user wants it: `block`, `warn`, `ask`, `retry`, `stop` or `log`.
- **Test before saving:** check each rule against commands it should and should not stop:
  `agentltl check --add draft.yaml "deny: git push --force" "allow: git push"`.
  Fix it until every line ends in `ok` and there is no `WARNING`.

Show the user the final `agentltl validate` output.

## 6. Finish

Tell the user:

1. **Activate it:** restart Codex. The plugin is active from then on, in every project that has
   an `AGENTLTL.yaml`.
2. **Try it:** ask Codex to do something a rule forbids, and watch it get refused with the
   rule's reason.
3. **Browse the library again:** `$agentltl:setup`.
4. **Add or remove rules in plain words:** `$agentltl:rules never touch the lockfile`, or just
   ask Codex.
5. **See what it is doing:** `$agentltl:status` shows the rules in force and what the guard
   recently blocked.
6. **Updating and removing:** `agentltl update`; `agentltl uninstall`, then
   `codex plugin remove agentltl@agentltl`.

## Troubleshooting

- **`agentltl: command not found`:** `~/.local/bin` is not on the PATH. Use
  `"${plugin}bin/agentltl"`.
- **Install fails with `ensurepip` or `No module named venv`:** install `python3-venv` (step 1).
- **Hooks never run:** they are not trusted yet. Run step 4, or approve them in `/hooks`.
- **Every call is refused with "AgentLTL ... is not installed":** the environment could not be
  built. Run step 4 and read its error.
- **A rule never fires:** run `agentltl validate` and fix any `WARNING`. It means a tool or
  argument name that no command produces.

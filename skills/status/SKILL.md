---
name: status
description: "Show the rules in force and what they blocked"
---
## The `agentltl` command

The steps below run `agentltl`. If it is not on the PATH, it is in the plugin folder Codex
installed:
`"$(ls -td "${CODEX_HOME:-$HOME/.codex}"/plugins/cache/agentltl/agentltl/*/ | head -1)"bin/agentltl`.
Use that path in its place, and offer the user `agentltl install-cli`, which puts it in
`~/.local/bin`.

Report on AgentLTL for Codex. Requested: what the user asked for (nothing more specific means `status`).

- **status**:
  1. Run `agentltl validate`, then `agentltl trace`.
  2. Summarise in a few lines:
     - which rules are in force, and their modes;
     - how many calls are recorded;
     - the recent interventions, and why.
  3. If the rule file has errors, show them first. Until they are fixed, nothing is enforced.
- **trace**: run `agentltl trace` and show the output.
- **reset**:
  1. Confirm with the user first, because it forgets which calls already happened. For example,
     tests already run will no longer count toward `before` rules.
  2. Then run `agentltl reset`.
- **check <steps>**: run `agentltl check <steps>` and explain each outcome.

To pick packaged rules, use the `$agentltl:setup` skill. To add, change or remove rules, use
the `$agentltl:rules` skill.

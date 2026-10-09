---
name: setup
description: "Pick ready-made rules to switch on. Use when: First setup of AgentLTL, or when the user asks which AGENTLTL rules are available, wants to browse, switch on or switch off packaged rules from the plugin's library, or says 'set up agentltl'."
---

# Choosing packaged rules

## The `agentltl` command

The steps below run `agentltl`. If it is not on the PATH, it is in the plugin folder Codex
installed:
`"$(ls -td "${CODEX_HOME:-$HOME/.codex}"/plugins/cache/agentltl/agentltl/*/ | head -1)"bin/agentltl`.
Use that path in its place, and offer the user `agentltl install-cli`, which puts it in
`~/.local/bin`.

The plugin ships a library of tested rules. Switching one on adds its name to the `use:` list
of `AGENTLTL.yaml`; the rule itself stays in the plugin and gets fixes with plugin updates.
`--user` (the user asked for rules everywhere) means rules for every project, in
`~/.codex/AGENTLTL.yaml`.

## Steps

1. **List the library**: run `agentltl library --json`. Each entry has a `name`, a `summary`,
   `tags`, `in_use` (already on in a file that applies here) and its rule ids.

2. **Ask where the rules go**, unless `--user` was given: this project (`AGENTLTL.yaml` at the
   project root) or every project (`~/.codex/AGENTLTL.yaml`). Rules for one repository's
   workflow (tests, deploys) usually belong to the project; personal habits (no Codex
   co-author) to every project.

3. **Let the user choose.** Ask the user (with the request_user_input tool in Plan mode,
   otherwise in your reply, ending your turn and waiting for the answer), a few entries at a
   time.
   - Group the entries by theme using their tags, for example "Git safety", "Files and
     secrets", or "Workflow and cost".
   - Show each entry's `name` and its `summary`.
   - Offer a bundle (an entry tagged `bundle`, such as `devops-secrets`) as one choice that
     switches on all the entries it lists.
   - Mark entries already on with "(on)". Tell the user that unticking one switches it off.
   - Outside Plan mode, number the entries in your reply and ask for the numbers.

4. **Ask about strictness** only if the user wants it. Every entry has a sensible default
   mode. To change it, use `agentltl use NAME --mode warn`. The modes are block, warn, ask,
   retry, stop and log; see the `$agentltl:rules` skill's reference.md.

5. **Apply the choices**, adding `--user` for every project:
   - `agentltl use NAME...` for the newly ticked entries;
   - `agentltl unuse NAME...` for the ones the user unticked.

   These commands edit only the `use:` list and keep the rest of the file. They create the file
   if it is missing.

6. **Check the result**: run `agentltl validate`. Then show the user the rules now in force,
   with each rule's mode and one line on what it does.
   - If a chosen rule depends on the project, say so. For example, `tests-before-push` knows
     common test runners (pytest, npm test, cargo test, make test...). If the project tests
     differently, offer to write a project rule with the same id: it replaces the packaged one.
   - `agentltl library NAME` shows a rule's YAML in full.

7. **Offer to scan memory**: run `agentltl memory scan --json`. If its
   `counts.candidates` is above 0, offer "Scan your instructions (AGENTS.md) for rules
   (N statements in M files)". If the user accepts, follow
   [the import skill](../import/SKILL.md) from its step 2, reusing
   that scan. Instructions already in memory then become rules that are enforced.

8. **Offer custom rules**: for anything the library and memory don't cover, use the
   `$agentltl:rules` skill to write a rule from the user's own words.

Changes apply from the next tool call. No restart is needed.

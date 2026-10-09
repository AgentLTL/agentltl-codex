"""AgentLTL rules in front of OpenAI Codex CLI's tool calls.

The rules, the guard, the hooks' logic and the library are agentltl_coding's; this package is
the Codex side: the hook I/O, where its instructions live, and the harness description below.
Rules use the canonical tool names (``Bash``, ``Write``, ``Edit``, ``Read``...), so the
library and a project's AGENTLTL.yaml work as in Claude Code. Codex's hooks already call its
shell tool ``Bash`` with a ``command``; an ``apply_patch`` call is split into the ``Write`` /
``Edit`` / ``rm`` calls it stands for (``patch.py``), and the files a shell command prints
(``cat``, ``sed -n``...) count as read (``hook.py``): Codex has no Read tool.
"""

import os

from agentltl_coding import Harness, configure


def codex_home() -> str:
    """Codex's configuration directory (``CODEX_HOME``, else ``~/.codex``)."""
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


# Codex's tools and their arguments, under the names rules use (``Bash`` and ``mcp__*`` are
# already Claude Code's names; ``apply_patch`` is expanded by the hook).
TOOL_ALIASES = {
    "spawn_agent": ("Task", {"message": "prompt", "agent_type": "subagent_type",
                             "task_name": "description"}),
    "view_image": ("Read", {"path": "file_path"}),
    "web_search": ("WebSearch", {}),
}

# Files Codex reads as instructions, and the ways a call writes them.
MEMORY_FILES = ["AGENTS.md", "AGENTS.override.md"]
MEMORY_FIRST = {
    "id": "memory-first",
    "never": [{"tool": ["Write", "Edit"], "where": {"file_path": MEMORY_FILES}},
              {"tool": "*", "where": {"redirect_to": MEMORY_FILES}},
              {"tool": ["tee", "sponge"], "where": {"*": MEMORY_FILES}}],
    "mode": "warn",
    "why": "AGENTLTL rules are enforced on every call; instructions can be forgotten. If what you "
           "are saving says which tool calls or commands to make, avoid, or make first (never X, "
           "always Y before Z, at most N times, only with these arguments), add it to "
           "AGENTLTL.yaml instead, using the $agentltl:rules skill, and leave it out of the "
           "instructions.",
    "fix": "Write the rule with the $agentltl:rules skill. Keep in the instructions only what no "
           "rule can check (facts, preferences, style). If nothing here can be a rule, repeat "
           "this exact call to save it.",
}
MEMORY_NOTE = ("before you add anything to instructions (AGENTS.md, AGENTS.override.md), ask "
               "whether it is a rule about tool calls or commands. If it is, add it to "
               "AGENTLTL.yaml with the $agentltl:rules skill instead: rules there are enforced, "
               "instructions can be forgotten.")


def _memory(root, user_only, home):
    from .memory import codex_sources
    return codex_sources(root, user_only, home)


CODEX = Harness(
    name="codex",
    agent="Codex",
    user_dir=os.environ.get("CODEX_HOME") or "~/.codex",
    shell_tools={"Bash": "command"},
    tool_aliases=TOOL_ALIASES,
    builtins={"memory_first": MEMORY_FIRST},
    # Codex's hooks say "bypassPermissions" when its approval policy is "never" (--yolo,
    # `codex exec` with approvals bypassed): nobody is there to answer.
    auto_modes=("bypassPermissions",),
    project_env="CODEX_PROJECT_DIR",
    skill="$agentltl:{}",
    memory=_memory,
    memory_note=MEMORY_NOTE,
)
configure(CODEX)

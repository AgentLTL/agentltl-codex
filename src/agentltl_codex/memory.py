"""
agentltl_codex/memory.py – where Codex's instructions live.

Codex reads, in each folder from the project root down to the working directory, the first of
``AGENTS.override.md`` and ``AGENTS.md`` (and the ``project_doc_fallback_filenames`` of its
config), and the user's ``~/.codex/AGENTS.override.md`` or ``~/.codex/AGENTS.md``.
:func:`codex_sources` lists the files that apply; the scanner is agentltl_coding's
(:mod:`agentltl_coding.memory`), re-exported here.
"""

from __future__ import annotations

import os
from typing import List

from agentltl_coding.memory import *  # noqa: F401,F403  (scan, split, decline, ...)
from agentltl_coding.memory import PROJECT, USER, Source, nested

NAMES = ("AGENTS.override.md", "AGENTS.md")


def codex_sources(root: str, user_only: bool, home: str) -> List[Source]:
    """The instruction files that apply in project *root*, then the user's. With *user_only*,
    only the user's."""
    base = os.environ.get("CODEX_HOME") or os.path.join(home, ".codex")
    user = [Source(os.path.join(base, name), "agents-md", USER) for name in NAMES]
    if user_only:
        return user
    out = [Source(os.path.join(root, name), "agents-md", PROJECT) for name in NAMES]
    for name in NAMES:
        out += [Source(p, "agents-md", PROJECT) for p in nested(root, name)]
    return out + user

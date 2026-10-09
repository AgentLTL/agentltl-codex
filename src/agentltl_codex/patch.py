"""
agentltl_codex/patch.py – what a Codex ``apply_patch`` call does, as the calls rules know.

Codex edits files with one freeform tool, ``apply_patch``, whose input is a patch that may
add, update, move and delete several files::

    *** Begin Patch
    *** Add File: notes.md          ->  Write {"file_path": "notes.md", "content": <+ lines>}
    +...
    *** Update File: src/app.py     ->  Edit  {"file_path": "src/app.py",
    @@ def main():                             "old_string": <- lines>, "new_string": <+ lines>}
    -    old
    +    new
    *** Move to: src/main.py        ->  ... and Write {"file_path": "src/main.py", ...}
    *** Delete File: old.txt        ->  Bash  {"command": "rm -- old.txt"}
    *** End Patch

so ``read-before-overwrite``, ``protect-env-files`` and every other rule on Write / Edit / rm
apply to it unchanged. (Codex's hooks give the patch as ``tool_input.command``.)
"""

from __future__ import annotations

import shlex
from typing import Any, Dict, List, Tuple

Call = Tuple[str, Dict[str, Any]]

_ADD, _UPDATE, _DELETE, _MOVE = "*** Add File: ", "*** Update File: ", "*** Delete File: ", \
    "*** Move to: "


def calls(patch: str) -> List[Call]:
    """The calls *patch* stands for, in order. A patch that can't be read gives no calls
    (Codex refuses it too, before anything is written)."""
    out: List[Call] = []
    current: Dict[str, Any] = {}

    def flush() -> None:
        if not current:
            return
        kind, path = current["kind"], current["path"]
        plus, minus = "\n".join(current["plus"]), "\n".join(current["minus"])
        if kind == "add":
            out.append(("Write", {"file_path": path, "content": plus + ("\n" if plus else "")}))
        elif kind == "update":
            out.append(("Edit", {"file_path": path, "old_string": minus, "new_string": plus}))
            if current.get("move"):
                out.append(("Write", {"file_path": current["move"], "content": plus}))
        current.clear()

    for line in (patch or "").splitlines():
        if line.startswith(_ADD):
            flush()
            current.update(kind="add", path=line[len(_ADD):].strip(), plus=[], minus=[])
        elif line.startswith(_UPDATE):
            flush()
            current.update(kind="update", path=line[len(_UPDATE):].strip(), plus=[], minus=[])
        elif line.startswith(_DELETE):
            flush()
            out.append(("Bash", {"command": "rm -- " + shlex.quote(line[len(_DELETE):].strip())}))
        elif line.startswith(_MOVE) and current.get("kind") == "update":
            current["move"] = line[len(_MOVE):].strip()
        elif line.startswith("*** "):          # Begin / End Patch, End of File
            continue
        elif current:
            if line.startswith("+"):
                current["plus"].append(line[1:])
            elif line.startswith("-"):
                current["minus"].append(line[1:])
    flush()
    return out


def paths(patch: str) -> List[str]:
    """The files *patch* touches (for messages)."""
    out = []
    for tool, args in calls(patch):
        out.append(args.get("file_path") or args.get("command", "").replace("rm -- ", "", 1))
    return out


__all__ = ["calls", "paths"]

"""
agentltl_codex/install.py – let Codex run AgentLTL's hooks: trust them in ``config.toml``.

Codex runs a plugin's hooks (``hooks/hooks.json``) only once each is trusted: the user
approves it in ``/hooks``, which saves its hash in ``~/.codex/config.toml``::

    [hooks.state."agentltl@agentltl:hooks/hooks.json:pre_tool_use:0:0"]
    trusted_hash = "sha256:..."

Until then the hooks are skipped without a word, in ``codex exec`` too. Installing writes
these entries for this plugin's hooks, between two marker comments at the end of the file;
uninstalling removes them. A hook whose definition changes (a plugin update) has a new hash
and needs ``agentltl install`` again. The hash is Codex's (``codex-rs/hooks/src/engine/
discovery.rs``, ``hook_hash``): SHA-256 of the key-sorted, compact JSON of the event's label,
the group's matcher and the handler with its defaults filled in.

Entries for these keys outside the block (an approval in ``/hooks``) are moved into it, so
the file never names a table twice; an ``enabled = false`` there is kept.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Dict, List, Tuple

from . import codex_home

BEGIN = "# >>> agentltl (managed by `agentltl install`; `agentltl uninstall` removes it)"
END = "# <<< agentltl"
_BLOCK = re.compile(r"\n*" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)

LABELS = {"PreToolUse": "pre_tool_use", "PermissionRequest": "permission_request",
          "PostToolUse": "post_tool_use", "PreCompact": "pre_compact",
          "PostCompact": "post_compact", "SessionStart": "session_start",
          "SessionEnd": "session_end", "UserPromptSubmit": "user_prompt_submit",
          "SubagentStart": "subagent_start", "SubagentStop": "subagent_stop", "Stop": "stop",
          "Interrupt": "interrupt"}
_SHORT = ("SessionEnd", "Interrupt")      # Codex: default 1 s, at most 3 s
_DEFAULT_CONTEXT_LIMIT = 2500
_CONTEXT_EVENTS = ("PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit",
                   "SubagentStart")


def config_file() -> str:
    return os.path.join(codex_home(), "config.toml")


def plugin_id(plugin_root: str) -> str:
    """``<plugin>@<marketplace>``: from where Codex installed it
    (``plugins/cache/<marketplace>/<plugin>/<version>``), else ``agentltl@agentltl``."""
    parts = os.path.normpath(os.path.abspath(plugin_root)).split(os.sep)
    if len(parts) >= 5 and parts[-5:-3] == ["plugins", "cache"]:
        return f"{parts[-2]}@{parts[-3]}"
    return "agentltl@agentltl"


def hook_hash(event: str, group: Dict, handler: Dict) -> str:
    """Codex's trust hash of one command handler."""
    if event in _SHORT:
        timeout = max(1, min(int(handler.get("timeout") or 1), 3))
    else:
        timeout = max(1, int(handler.get("timeout") or 600))
    normal = {"type": "command", "command": handler["command"], "timeout": timeout,
              "async": bool(handler.get("async", False))}
    if handler.get("statusMessage") is not None:
        normal["statusMessage"] = handler["statusMessage"]
    limit = handler.get("additionalContextLimit")
    if event in _CONTEXT_EVENTS and limit is not None and limit != _DEFAULT_CONTEXT_LIMIT:
        normal["additionalContextLimit"] = limit
    identity = {"event_name": LABELS[event], "hooks": [normal]}
    if group.get("matcher") is not None:
        identity["matcher"] = group["matcher"]
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def entries(plugin_root: str) -> Dict[str, str]:
    """Trust key -> hash, for every hook in the plugin's ``hooks/hooks.json``."""
    with open(os.path.join(plugin_root, "hooks", "hooks.json"), encoding="utf-8") as fh:
        hooks = json.load(fh)["hooks"]
    source = f"{plugin_id(plugin_root)}:hooks/hooks.json"
    out = {}
    for event, groups in hooks.items():
        for gi, group in enumerate(groups):
            for hi, handler in enumerate(group.get("hooks") or []):
                if handler.get("type") == "command":
                    out[f"{source}:{LABELS[event]}:{gi}:{hi}"] = hook_hash(event, group, handler)
    return out


def block(plugin_root: str, disabled: Tuple[str, ...] = ()) -> str:
    lines = [BEGIN, "# Codex runs a hook only once it is trusted; these are AgentLTL's."]
    for key, digest in entries(plugin_root).items():
        lines += ["", f"[hooks.state.{_toml_str(key)}]", f"trusted_hash = {_toml_str(digest)}"]
        if key in disabled:
            lines.append("enabled = false")
    return "\n".join(lines + [END, ""])


def install(plugin_root: str) -> Tuple[bool, str]:
    path = config_file()
    text = _read(path)
    keys = list(entries(plugin_root))
    rest, disabled = _drop_tables(_BLOCK.sub("\n", text), keys)
    rest = rest.strip("\n")
    new = (rest + "\n\n" if rest else "") + block(plugin_root, tuple(disabled))
    problem = _toml_problem(new)
    if problem:
        return False, (f"{path} would not be valid TOML with AgentLTL's entries ({problem}); "
                       "nothing was changed. Fix the file, or approve AgentLTL's hooks in "
                       "Codex's /hooks.")
    if new == text:
        return True, f"AgentLTL's hooks are already trusted in {path}."
    _write(path, new)
    verb = "Updated" if _BLOCK.search(text) else "Added"
    return True, (f"{verb} the trust of AgentLTL's {len(keys)} hooks in {path}. They run from "
                  "the next Codex session.")


def uninstall() -> Tuple[bool, str]:
    path = config_file()
    text = _read(path)
    if not _BLOCK.search(text):
        return True, f"AgentLTL's hooks are not trusted in {path}."
    rest = _BLOCK.sub("\n", text).strip("\n")
    _write(path, rest + "\n" if rest else "")
    return True, f"Removed the trust of AgentLTL's hooks from {path}; Codex won't run them."


def installed(plugin_root: str) -> bool:
    """Whether every hook of this plugin version is trusted."""
    text = _read(config_file())
    m = _BLOCK.search(text)
    return bool(m) and all(f"[hooks.state.{_toml_str(k)}]\ntrusted_hash = {_toml_str(v)}"
                           in m.group(0) for k, v in entries(plugin_root).items())


# ── the file ──────────────────────────────────────────────────────────────────

_HEADER = re.compile(r"^\s*\[", re.M)


def _drop_tables(text: str, keys: List[str]) -> Tuple[str, List[str]]:
    """*text* without the ``[hooks.state."<key>"]`` tables of *keys*, and the keys among them
    the user switched off (``enabled = false``)."""
    disabled = []
    for key in keys:
        header = re.compile(r"^\s*\[\s*hooks\s*\.\s*state\s*\.\s*" + re.escape(_toml_str(key))
                            + r"\s*\]\s*(#.*)?$", re.M)
        m = header.search(text)
        while m:
            nxt = _HEADER.search(text, m.end())
            end = nxt.start() if nxt else len(text)
            if re.search(r"^\s*enabled\s*=\s*false\b", text[m.end():end], re.M):
                disabled.append(key)
            text = text[:m.start()] + text[end:]
            m = header.search(text)
    return text, disabled


def _toml_problem(text: str) -> str:
    try:
        import tomllib
    except ImportError:          # Python 3.10: no parser at hand; Codex will say
        return ""
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return str(exc)
    return ""


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".agentltl-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    if os.path.exists(path):
        os.chmod(tmp, os.stat(path).st_mode & 0o777)
    os.replace(tmp, path)


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


__all__ = ["BEGIN", "END", "block", "config_file", "entries", "hook_hash", "install",
           "installed", "plugin_id", "uninstall"]

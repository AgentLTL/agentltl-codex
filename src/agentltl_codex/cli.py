"""
agentltl_codex/cli.py – the ``agentltl`` command of the Codex plugin.

Everything agentltl_coding's command does (validate, check, translate, tools, trace, reset,
library, use/unuse, disable/enable, and memory scan/decline/forget over Codex's instructions),
plus what is Codex's own:

    agentltl install [--no-cli]          trust AgentLTL's hooks in ~/.codex/config.toml (Codex
                                         runs no hook until it is trusted), and put `agentltl`
                                         on your PATH (~/.local/bin)
    agentltl uninstall                   remove that trust: Codex stops running the hooks (the
                                         plugin and the rule files stay)
    agentltl update                      get the latest plugin version, then install again
    agentltl install-cli [--dir DIR]     only the command

``check`` steps name the calls rules see: an ``apply_patch`` as the ``Write`` / ``Edit`` / ``rm``
calls it stands for (``'Write {"file_path": ".env", "content": "x"}'``).
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

from agentltl_coding.cli import main as _main

from . import CODEX  # noqa: F401  (configures the harness)

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WRAPPER_MARK = "# agentltl for Codex (written by `agentltl install-cli`)"


def main(argv: Optional[List[str]] = None) -> int:
    return _main(argv, extend=_extend)


def _extend(sub: Any, commands: Dict[str, Callable[[argparse.Namespace], int]]) -> None:
    p = sub.add_parser("install", help="trust AgentLTL's hooks in Codex (~/.codex/config.toml)")
    p.add_argument("--no-cli", action="store_true", help="don't put `agentltl` in ~/.local/bin")
    sub.add_parser("uninstall", help="stop Codex from running AgentLTL's hooks")
    sub.add_parser("update", help="get the latest plugin version and install it")
    p = sub.add_parser("install-cli", help="put `agentltl` on your PATH")
    p.add_argument("--dir", default=os.path.join("~", ".local", "bin"),
                   help="where to put the command (default: ~/.local/bin)")
    commands["install"] = _install
    commands["uninstall"] = _uninstall
    commands["update"] = _update
    commands["install-cli"] = _install_cli


def _install(args: argparse.Namespace) -> int:
    from . import install
    ok, message = install.install(PLUGIN_ROOT)
    print(message, file=sys.stdout if ok else sys.stderr)
    if ok and not getattr(args, "no_cli", False):
        _install_cli(argparse.Namespace(dir=os.path.join("~", ".local", "bin")), quiet_clash=True)
    return 0 if ok else 1


def _uninstall(args: argparse.Namespace) -> int:
    from . import install
    ok, message = install.uninstall()
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def _cache_dir() -> Optional[str]:
    """``.../plugins/cache/<marketplace>/<plugin>`` when Codex installed this plugin, else None
    (a git checkout)."""
    parts = os.path.normpath(PLUGIN_ROOT).split(os.sep)
    return os.path.dirname(PLUGIN_ROOT) if parts[-5:-3] == ["plugins", "cache"] else None


def _newest() -> str:
    """The newest installed version's directory (this one outside Codex's cache)."""
    cache = _cache_dir()
    if not cache:
        return PLUGIN_ROOT
    versions = [d for d in glob.glob(os.path.join(cache, "*")) if os.path.isdir(d)]
    return max(versions, key=os.path.getmtime) if versions else PLUGIN_ROOT


def _update(args: argparse.Namespace) -> int:
    if _cache_dir():
        from .install import plugin_id
        pid = plugin_id(PLUGIN_ROOT)
        marketplace = pid.split("@", 1)[1]
        for cmd in (["codex", "plugin", "marketplace", "upgrade", marketplace],
                    ["codex", "plugin", "add", pid]):
            try:
                if subprocess.run(cmd).returncode != 0:
                    return 1
            except FileNotFoundError:
                print("`codex` is not on your PATH; run: codex plugin marketplace upgrade "
                      f"{marketplace} && codex plugin add {pid}", file=sys.stderr)
                return 1
    elif os.path.isdir(os.path.join(PLUGIN_ROOT, ".git")):
        for cmd in (["git", "pull", "--ff-only"],
                    ["git", "submodule", "update", "--init", "--recursive"]):
            if subprocess.run(cmd, cwd=PLUGIN_ROOT).returncode != 0:
                return 1
    else:
        print(f"{PLUGIN_ROOT} is neither installed by Codex nor a git checkout; update it the "
              "way you installed it.", file=sys.stderr)
        return 1
    # The new version's code runs in a new process: its own install, its own environment.
    return subprocess.run([os.path.join(_newest(), "bin", "agentltl"), "install"]).returncode


def _wrapper(cache: str) -> str:
    return "\n".join([
        "#!/usr/bin/env bash",
        WRAPPER_MARK,
        "# Runs the newest AgentLTL plugin version Codex installed.",
        f'cache="{cache}"',
        'newest="$(ls -td "$cache"/*/ 2>/dev/null | head -1)"',
        '[[ -n "$newest" ]] || { echo "agentltl: the Codex plugin is not installed in $cache" >&2;'
        " exit 1; }",
        'exec "${newest%/}/bin/agentltl" "$@"',
        ""])


def _install_cli(args: argparse.Namespace, quiet_clash: bool = False) -> int:
    folder = os.path.expanduser(args.dir)
    target = os.path.join(PLUGIN_ROOT, "bin", "agentltl")
    link = os.path.join(folder, "agentltl")
    cache = _cache_dir()
    if os.path.lexists(link):
        if os.path.realpath(link) == os.path.realpath(target):
            return 0
        if cache and not os.path.islink(link) and WRAPPER_MARK in _read(link):
            if _read(link) == _wrapper(cache):
                return 0
        else:
            print(f"{link} exists and is not this plugin's; not replaced. Run {target} "
                  "directly.", file=sys.stderr)
            return 0 if quiet_clash else 1
    os.makedirs(folder, exist_ok=True)
    if cache:   # Codex installs each version in its own directory: run the newest
        tmp = link + ".agentltl-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(_wrapper(cache))
        os.chmod(tmp, 0o755)
        os.replace(tmp, link)
        shown = f"{link} (runs the newest version in {cache})"
    else:
        os.symlink(target, link)
        shown = f"{link} -> {target}"
    on_path = folder in os.environ.get("PATH", "").split(os.pathsep)
    print(shown + ("" if on_path else f"\n{folder} is not on your PATH yet."))
    return 0


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(4096)
    except OSError:
        return ""


__all__ = ["main"]

if __name__ == "__main__":
    sys.exit(main())

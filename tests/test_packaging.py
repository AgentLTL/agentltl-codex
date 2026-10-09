"""vendor.lock must pin what the vendor/ submodules pin: it is what a marketplace install,
which has no submodules, installs from."""

import json
import os
import subprocess

import pytest
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _gitlinks():
    try:
        out = subprocess.run(["git", "ls-files", "-s", "vendor"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return {line.split()[3]: line.split()[1] for line in out.splitlines() if line.startswith("160000")}


def test_vendor_lock_matches_the_submodules():
    links = _gitlinks()
    pinned = {}
    with open(os.path.join(ROOT, "vendor.lock")) as fh:
        for line in fh:
            if line.strip() and not line.startswith("#"):
                name, _url, commit = line.split()
                pinned["vendor/" + ("AgentLTL" if name == "agentltl" else name)] = commit
    assert pinned == links


def _json(*path):
    with open(os.path.join(ROOT, *path)) as fh:
        return json.load(fh)


def test_manifests():
    manifest = _json(".codex-plugin", "plugin.json")
    market = _json(".agents", "plugins", "marketplace.json")
    assert manifest["name"] == market["name"] == market["plugins"][0]["name"] == "agentltl"
    assert market["plugins"][0]["source"] == {"source": "local", "path": "./"}
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        assert tomllib.load(fh)["project"]["version"] == manifest["version"]
    for skill in ("setup", "rules", "import", "status"):
        assert os.path.isfile(os.path.join(ROOT, manifest["skills"], skill, "SKILL.md"))


def test_hooks_json_runs_the_launcher_for_events_the_hook_handles():
    hooks = _json("hooks", "hooks.json")["hooks"]
    assert set(hooks) == {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                          "SubagentStart", "Stop"}
    for event, groups in hooks.items():
        (group,) = groups
        (handler,) = group["hooks"]
        assert handler["command"] == f'"${{PLUGIN_ROOT}}/hooks/run" {event}'
    assert hooks["PreToolUse"][0]["hooks"][0]["timeout"] >= 120     # the first call builds the venv

"""`agentltl install` trusts AgentLTL's hooks in ~/.codex/config.toml: only its own entries,
idempotently, with the hashes Codex computes."""

import json
import os

import pytest
import tomllib

from agentltl_codex import install

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USER_CONFIG = '''model = "gpt-5.5"

[projects."/home/me/src"]
trust_level = "trusted"
'''


@pytest.fixture
def codex_home(tmp_path, monkeypatch):
    home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def _config(home):
    with open(home / "config.toml", "rb") as fh:
        return tomllib.load(fh)


def test_hashes_are_codexs():
    # Hashes Codex 0.162.0 accepted (docker/spike: hooks ran without --dangerously-bypass-hook-trust)
    probe = {"command": "python3 /opt/agentltl/probe.py", "timeout": 30}
    assert install.hook_hash("PreToolUse", {}, probe) == \
        "sha256:713a1e393b349190861d48659d2a1b960e21de1840fe1e7c0dfbdb1300089e81"
    assert install.hook_hash("SessionEnd", {}, probe) == \
        "sha256:c1174bf85692b7bdcb0decdade1b90db844a33836372dea71eee3428091bab1d"
    # the default timeout counts, and a matcher changes the hash
    assert install.hook_hash("Stop", {}, {"command": "x"}) == \
        install.hook_hash("Stop", {}, {"command": "x", "timeout": 600})
    assert install.hook_hash("PreToolUse", {"matcher": "*"}, {"command": "x"}) != \
        install.hook_hash("PreToolUse", {}, {"command": "x"})


def test_every_hook_of_the_plugin_is_trusted(codex_home):
    with open(os.path.join(ROOT, "hooks", "hooks.json")) as fh:
        n = sum(len(g["hooks"]) for groups in json.load(fh)["hooks"].values() for g in groups)
    ok, message = install.install(ROOT)
    assert ok and message.startswith("Added")
    state = _config(codex_home)["hooks"]["state"]
    assert len(state) == n == len(install.entries(ROOT))
    key = "agentltl@agentltl:hooks/hooks.json:pre_tool_use:0:0"
    assert state[key]["trusted_hash"].startswith("sha256:")
    assert install.installed(ROOT)


def test_install_keeps_the_users_config_and_is_idempotent(codex_home):
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(USER_CONFIG)
    assert install.install(ROOT)[0]
    once = (codex_home / "config.toml").read_text()
    assert once.startswith(USER_CONFIG)
    ok, message = install.install(ROOT)
    assert ok and "already" in message
    assert (codex_home / "config.toml").read_text() == once
    config = _config(codex_home)
    assert config["model"] == "gpt-5.5" and config["projects"]["/home/me/src"]
    assert install.uninstall()[0]
    assert (codex_home / "config.toml").read_text() == USER_CONFIG
    assert not install.installed(ROOT)


def test_an_approval_in_hooks_is_taken_over(codex_home):
    """Codex's /hooks saved its own entries for two of AgentLTL's hooks (one switched off):
    install replaces them, so no table is named twice, and keeps the switch."""
    codex_home.mkdir()
    pre = "agentltl@agentltl:hooks/hooks.json:pre_tool_use:0:0"
    stop = "agentltl@agentltl:hooks/hooks.json:stop:0:0"
    (codex_home / "config.toml").write_text(
        USER_CONFIG + f'\n[hooks.state."{pre}"]\ntrusted_hash = "sha256:old"\n'
        f'\n[hooks.state."{stop}"]\nenabled = false\ntrusted_hash = "sha256:old"\n'
        '\n[tui]\nstatus_line = ["model"]\n')
    assert install.install(ROOT)[0]
    config = _config(codex_home)
    assert config["hooks"]["state"][pre]["trusted_hash"] != "sha256:old"
    assert config["hooks"]["state"][stop]["enabled"] is False
    assert config["tui"] == {"status_line": ["model"]}


def test_a_broken_config_is_left_alone(codex_home):
    codex_home.mkdir()
    (codex_home / "config.toml").write_text("model = \n")
    ok, message = install.install(ROOT)
    assert not ok and "nothing was changed" in message
    assert (codex_home / "config.toml").read_text() == "model = \n"


def test_the_plugin_id_comes_from_codexs_cache(tmp_path):
    cached = tmp_path / ".codex" / "plugins" / "cache" / "mine" / "agentltl" / "0.1.0"
    assert install.plugin_id(str(cached)) == "agentltl@mine"
    assert install.plugin_id(ROOT) == "agentltl@agentltl"

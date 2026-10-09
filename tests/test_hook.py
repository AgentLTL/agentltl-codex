"""The hook end to end: Codex hook payloads in, hook JSON out."""

import json
import os
import subprocess
import sys

import pytest
from agentltl_coding import store

from agentltl_codex import hook

RULES = """
rules:
  - id: tests-before-push
    before: {first: pytest, then: git_push, since: [Edit, Write]}
    why: CI is slow.
  - id: no-secrets
    never: [Read, Edit, cat]
    where: {"*": "**/.env"}
    mode: stop
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "AGENTLTL.yaml").write_text(RULES)
    return root


def event(project, name, tool=None, args=None, **extra):
    payload = {"hook_event_name": name, "session_id": "s1", "turn_id": "t1",
               "transcript_path": str(project / "no-rollout.jsonl"), "cwd": str(project),
               "model": "gpt-5.5", "permission_mode": "default", **extra}
    if tool:
        payload.update(tool_name=tool, tool_input=args or {})
        payload.setdefault("tool_use_id", "call_1")
    return hook.run(name, payload)


def pre(project, tool, args, **kw):
    return event(project, "PreToolUse", tool, args, **kw)


def post(project, tool, args, text="", **kw):
    return event(project, "PostToolUse", tool, args, tool_response=text, **kw)


def prompt(project, text="go on", **kw):
    return event(project, "UserPromptSubmit", prompt=text, **kw)


def stop(project, **kw):
    return event(project, "Stop", stop_hook_active=False, last_assistant_message="Done.", **kw)


def bash(command):
    return "Bash", {"command": command}


def apply_patch(*lines):
    return "apply_patch", {"command": "\n".join(["*** Begin Patch", *lines, "*** End Patch", ""])}


def decision(out):
    return out and out["hookSpecificOutput"].get("permissionDecision")


def reason(out):
    return out["hookSpecificOutput"]["permissionDecisionReason"]


def completed(sid="s1"):
    return [(c["tool_name"], c.get("status")) for c in store.read(sid)["completed_tool_calls"]]


def test_scenario(project):
    deny = pre(project, *bash("git push"))
    assert decision(deny) == "deny" and "tests-before-push" in reason(deny)
    assert deny["systemMessage"] == "AgentLTL: rule 'tests-before-push' refused Bash git push"

    post(project, *bash("pytest -q"), "3 passed")
    assert pre(project, *bash("git push")) is None              # silent: no objection

    # an edit that was proposed but never ran does not count; one that ran does
    edit = apply_patch("*** Update File: a.py", "@@", "-a", "+b")
    assert pre(project, *edit) is None
    assert pre(project, *bash("git push")) is None
    post(project, *edit, "Success. Updated the following files:\nM a.py\n")
    assert decision(pre(project, *bash("git push"))) == "deny"


def test_session_start_lists_the_rules(project):
    out = event(project, "SessionStart", source="startup")
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "tests-before-push" in text and "memory-first" in text and "$agentltl:rules" in text
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert out["systemMessage"] == "AgentLTL: 3 rule(s) in force"
    child = event(project, "SubagentStart", agent_id="a1", agent_type="default")
    assert "tests-before-push" in child["hookSpecificOutput"]["additionalContext"]
    (project / "AGENTLTL.yaml").write_text("settings: {announce: false}\n" + RULES)
    assert event(project, "SessionStart", source="startup") is None


def test_apply_patch_is_the_writes_and_edits_it_stands_for(project):
    (project / "AGENTLTL.yaml").write_text(
        "use: [read-before-overwrite]\nrules: [{id: no-env, never: Write, where: "
        "{file_path: '**/.env'}}, {id: no-rm, never: rm}]")
    (project / "README.md").write_text("hello\n")
    overwrite = apply_patch("*** Add File: new.txt", "+one", "*** Add File: README.md", "+x")
    out = pre(project, *overwrite)
    assert decision(out) == "deny" and "read-before-overwrite" in reason(out)
    assert "README.md" in out["systemMessage"] and "new.txt" in out["systemMessage"]
    assert pre(project, *apply_patch("*** Add File: new.txt", "+one")) is None
    post(project, *bash("cat README.md"), "hello\n")              # Codex reads with the shell
    assert pre(project, *overwrite) is None
    moved = apply_patch("*** Update File: a.py", "*** Move to: .env", "@@", "-a", "+b")
    assert "no-env" in reason(pre(project, *moved))
    assert "no-rm" in reason(pre(project, *apply_patch("*** Delete File: old.txt")))


def test_what_a_command_prints_counts_as_read(project):
    (project / "AGENTLTL.yaml").write_text("use: [read-before-overwrite]")
    for name in ("a", "b", "c", "d", "e"):
        (project / name).write_text("x\n")

    def overwrite(name):
        return pre(project, *apply_patch(f"*** Add File: {name}", "+y"))

    post(project, *bash("sed -n 1,20p a; head -3 b && cd sub 2>/dev/null; nl -ba c"), "x")
    assert [decision(overwrite(n)) for n in "abcde"] == [None, None, None, "deny", "deny"]
    post(project, *bash("sed -i s/x/y/ d"), "")                    # an edit is not a read
    assert decision(overwrite("d")) == "deny"
    post(project, *bash("cat e"), "", tool_use_id="call_9",
         transcript_path=str(rollout(project, "call_9", 1)))      # it failed: nothing shown
    assert decision(overwrite("e")) == "deny"


def rollout(project, call_id, exit_code):
    path = project / "rollout.jsonl"
    with open(path, "a") as fh:
        fh.write(json.dumps({"type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "CommandExecution", "id": call_id, "exit_code": exit_code}}}) + "\n")
    return path


def test_a_command_that_failed_has_status_1(project):
    path = rollout(project, "call_7", 2)
    rollout(project, "call_8", 0)
    post(project, *bash("pytest"), "1 failed", tool_use_id="call_7", transcript_path=str(path))
    post(project, *bash("ls"), "a", tool_use_id="call_8", transcript_path=str(path))
    post(project, *bash("make"), "", tool_use_id="call_x", transcript_path="/nonexistent")
    assert completed() == [("pytest", 1), ("ls", 0), ("make", 0)]


def test_stop_denies_everything_until_the_user_writes(project):
    out = pre(project, *bash("cat .env"))
    assert decision(out) == "deny" and "stops the session" in reason(out)
    assert "no tool runs until you reply" in out["systemMessage"]
    held = pre(project, *bash("ls"))
    assert decision(held) == "deny" and "stopped this session" in reason(held)
    prompt(project, "CHILD task", agent_id="a1", agent_type="default")   # a subagent's task
    assert decision(pre(project, *bash("ls"))) == "deny"
    prompt(project)                                         # the user wrote
    assert pre(project, *bash("ls")) is None


def test_ask_rules_refuse_until_codex_has_asked_the_user(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-rm, never: rm, mode: ask}]")
    rm = bash("rm -rf build")
    out = pre(project, *rm)
    assert decision(out) == "deny" and "no-rm" in reason(out)
    assert "in your reply" in reason(out) and "Allow this call anyway?" not in reason(out)
    assert decision(pre(project, *rm)) == "deny"         # repeating alone is not enough
    prompt(project, "yes, go ahead")
    assert pre(project, *rm) is None                     # asked: goes through, once
    assert [d["action"] for d in store.read("s1")["decisions"]] == ["ask", "ask", "ok"]
    assert decision(pre(project, *rm)) == "deny"
    assert decision(pre(project, *bash("rm -rf dist"))) == "deny"   # only that call


def test_ask_answered_with_request_user_input(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-rm, never: rm, mode: ask}]")
    assert decision(pre(project, *bash("rm x"))) == "deny"
    post(project, "request_user_input", {"questions": [{"id": "q", "question": "rm x?"}]},
         '{"answers": {"q": {"answers": ["Yes"]}}}')
    assert pre(project, *bash("rm x")) is None


def test_ask_rules_unattended_are_refused(project, monkeypatch):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-rm, never: rm, mode: ask}]")
    out = pre(project, *bash("rm x"), permission_mode="bypassPermissions")
    assert decision(out) == "deny" and "unattended" in reason(out)
    prompt(project)
    assert decision(pre(project, *bash("rm x"), permission_mode="bypassPermissions")) == "deny"
    monkeypatch.setenv("AGENTLTL_AUTO", "1")
    assert "unattended" in reason(pre(project, *bash("rm y")))
    monkeypatch.setenv("AGENTLTL_AUTO", "0")          # someone is there despite --yolo
    out = pre(project, *bash("rm z"), permission_mode="bypassPermissions")
    assert "in your reply" in reason(out)
    prompt(project)
    assert pre(project, *bash("rm z"), permission_mode="bypassPermissions") is None


def test_a_note_on_an_allowed_call(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-sudo, never: sudo, mode: log, why: w}]")
    out = pre(project, *bash("sudo ls"))
    assert "permissionDecision" not in out["hookSpecificOutput"]
    assert "no-sudo" in out["hookSpecificOutput"]["additionalContext"]


def test_credentials_in_output(project):
    out = post(project, *bash("cat config"), "key=" + "AKIA" + "ABCDEFGHIJKLMNOP")
    assert "AWS access key ID" in out["hookSpecificOutput"]["additionalContext"]
    assert "AWS access key ID" in out["systemMessage"]


def test_a_finally_rule_sends_codex_back_once_per_turn(project):
    (project / "AGENTLTL.yaml").write_text("settings: {finish_retries: 1}\n"
                                           "rules: [{id: tested, finally: pytest}]")
    first = stop(project)
    assert first["decision"] == "block" and "tested" in first["reason"]
    assert first["systemMessage"].startswith("AgentLTL sent Codex back:")
    assert stop(project) is None                    # retries used up: the turn ends
    prompt(project)                                 # the user wrote again
    assert stop(project)["decision"] == "block"
    post(project, *bash("pytest"), "ok")
    assert stop(project) is None


def test_broken_file_is_told_at_session_start_and_calls_go_ahead(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: x, nevr: rm}]")
    out = event(project, "SessionStart", source="startup")
    assert "NO AGENTLTL rules are being enforced" in out["hookSpecificOutput"]["additionalContext"]
    assert pre(project, *bash("rm x")) is None
    assert post(project, *bash("rm x")) is None


def test_no_rule_file_is_silent(tmp_path):
    (tmp_path / ".git").mkdir()
    assert hook.run("PreToolUse", {"cwd": str(tmp_path), "tool_name": "Bash",
                                   "tool_input": {"command": "rm -rf /"}}) is None


def test_internal_error_denies_instead_of_failing_open(project, monkeypatch):
    from agentltl_coding import Session
    monkeypatch.setattr(Session, "pre", lambda *a, **k: 1 / 0)
    out = pre(project, *bash("ls"))
    assert decision(out) == "deny" and "could not be checked" in reason(out)


def test_subagent_calls_are_checked_in_the_parent_session(project):
    child = {"agent_id": "a1", "agent_type": "default"}
    post(project, *bash("pytest"), "ok", **child)
    assert pre(project, *bash("git push")) is None
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-kids, never: Task}]")
    out = pre(project, "spawn_agent", {"message": "look around"})
    assert decision(out) == "deny" and "no-kids" in reason(out)


def test_project_memory_spans_sessions(project):
    (project / "AGENTLTL.yaml").write_text(
        "rules: [{id: tests-ever, before: [pytest, git_push], scope: project}]")
    post(project, *bash("pytest"), session_id="a")
    assert pre(project, *bash("git push"), session_id="b") is None
    assert store.read("b").get("project_dir") == str(project)


def test_the_project_is_codex_project_dir(project, monkeypatch):
    sub = project / "src"
    sub.mkdir()
    monkeypatch.setenv("CODEX_PROJECT_DIR", str(project))
    assert decision(pre(project, *bash("git push"), cwd=str(sub))) == "deny"
    assert store.read("s1")["project_dir"] == str(project)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def launch(project, python, event_name="PreToolUse"):
    env = dict(os.environ, AGENTLTL_CODEX_PYTHON=python, PYTHONPATH=os.pathsep.join(sys.path))
    payload = json.dumps({"session_id": "s1", "cwd": str(project), "tool_name": "Bash",
                          "hook_event_name": event_name, "tool_use_id": "c",
                          "tool_input": {"command": "git push"}})
    out = subprocess.run([os.path.join(ROOT, "hooks", "run"), event_name], input=payload,
                         capture_output=True, text=True, env=env, cwd=str(project))
    assert out.returncode == 0            # Codex lets a call through when a hook fails
    return json.loads(out.stdout) if out.stdout else None


def test_launcher(project):
    """hooks/run with the test Python: payload on stdin, JSON on stdout."""
    assert decision(launch(project, sys.executable)) == "deny"


def test_launcher_denies_when_python_fails(project, tmp_path):
    broken = tmp_path / "python"
    broken.write_text("#!/bin/sh\nexit 3\n")
    broken.chmod(0o755)
    out = launch(project, str(broken))
    assert decision(out) == "deny" and "crashed" in reason(out)
    assert launch(project, str(broken), "PostToolUse") is None


# ── what Codex 0.162.0 actually sends (tests/fixtures/payloads) ────────────────

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "payloads", "codex-0.162.0.json")


def test_captured_session_replays(tmp_path):
    root = tmp_path / "work"
    (root / ".git").mkdir(parents=True)
    (root / "README.md").write_text("hello\n")
    (root / "AGENTLTL.yaml").write_text("use: [no-codex-coauthor, read-before-overwrite]\n")
    with open(FIXTURE) as fh:
        data = json.load(fh)
    rollouts = {}
    for i, (path, lines) in enumerate(data["transcripts"].items()):
        local = tmp_path / f"rollout-{i}.jsonl"
        local.write_text("".join(json.dumps(line) + "\n" for line in lines))
        rollouts[path] = str(local)
    answers = []
    for e in data["sessions"][0]:
        raw = json.dumps(e["payload"])
        for path, local in rollouts.items():
            raw = raw.replace(path, local)
        payload = json.loads(raw.replace('"/work', '"' + str(root)))
        out = hook.run(e["event"], payload)
        if e["event"] == "PreToolUse":
            answers.append((payload["tool_name"], decision(out)))
    assert answers == [
        ("Bash", None), ("apply_patch", "deny"), ("Bash", None), ("apply_patch", None),
        ("Bash", None), ("Bash", None), ("Bash", None), ("Bash", None), ("spawn_agent", None),
        ("Bash", None), ("Bash", None), ("Bash", "deny"), ("Bash", None)]
    sid = data["sessions"][0][0]["payload"]["session_id"]
    calls = completed(sid)
    assert ("false", 1) in calls and ("ls", 1) in calls     # exit codes from the rollout
    assert ("Read", 0) in calls and ("Task", 0) in calls and ("pwd", 0) in calls

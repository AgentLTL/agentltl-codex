"""
agentltl_codex/hook.py – the Codex hook: ``python -m agentltl_codex.hook EVENT`` reads the
event JSON on stdin and prints the hook's JSON answer (``hooks/hooks.json``).

    SessionStart      remind Codex of the rules (also after a resume, a /clear, a compaction)
    SubagentStart     the same for a subagent, whose calls are checked as Codex's own
    UserPromptSubmit  the user wrote: lift a `stop`, let `finally` rules send Codex back again,
                      and let a call an `ask` rule refused go through once if repeated
    PreToolUse        deny a call that breaks a rule (a `stop` denies every call until the
                      user writes), else stay silent or pass on the rules' note
    PostToolUse       add the call that ran to the session and project traces (status 0, or
                      1 for a command that exited non-zero); warn when its output holds a
                      credential
    Stop              Codex is about to finish: while a `finally` rule is unmet, send it back
                      with what is missing (at most settings.finish_retries times a turn)

Without an AGENTLTL.yaml (project or ``~/.codex``) it exits at once. It never approves a call:
silence leaves the decision to Codex's own approvals. Codex lets a call through when a hook
fails, so an internal error during PreToolUse denies the call (and ``hooks/run`` denies when
Python itself fails).

What Codex's hooks lack, and what this does instead:

- no "ask" answer: an `ask` rule refuses the call and tells Codex to ask the user in its reply
  and end its turn; after the user writes (or answers ``request_user_input`` in Plan mode),
  the exact same call goes through once;
- no Read tool: the files a shell command prints in full (``cat``, ``head``, ``sed -n``...)
  are recorded as ``Read`` calls, so `read-before-overwrite` holds;
- ``apply_patch`` edits many files at once: it is checked and recorded as the Write / Edit /
  ``rm`` calls it stands for (``patch.py``);
- no exit code in a command's result: it is read from the session's rollout file.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from . import (
    CODEX,  # noqa: F401  (configures the harness)
    patch,
)

_ASKS = "codex_asks"                   # call key -> "asked" | "answered"
ASK_TOOL = "request_user_input"
PATCH_TOOL = "apply_patch"
_RANK = {"none": 0, "ask": 1, "deny": 2, "stop": 3}

# Commands whose output is the files they are given (all, or a part the agent chose).
VIEWERS = {"cat", "head", "tail", "sed", "nl", "less", "more", "bat", "batcat", "tac"}

_ASK_TAIL = (
    "Nothing was executed. Codex's hooks can't ask the user directly, so do it yourself: show "
    "the user this call and why the rule asks for approval in your reply, and end your turn "
    "there (in Plan mode you may use the request_user_input tool). If they approve, repeat "
    "exactly the same call and it will go through. If they decline, don't retry it or work "
    "around the rule; ask them what they want instead.")


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    out = run(argv[0] if argv else "", payload if isinstance(payload, dict) else {})
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


def run(event: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The hook's answer to one event, or None for no output."""
    event = event or payload.get("hook_event_name", "")
    try:
        from agentltl_coding import Session
        from agentltl_coding.cli import _git_root
        cwd = payload.get("cwd") or os.getcwd()
        project = os.environ.get("CODEX_PROJECT_DIR") or _git_root(cwd) or cwd
        session = Session(cwd, project, payload.get("session_id"))
        if not session.files:
            return None
        return _handle(event, payload, session)
    except Exception as exc:  # the guard must not fail open silently
        return _failure(event, exc)


def _handle(event: str, payload: Dict[str, Any], session: Any) -> Optional[Dict[str, Any]]:
    from agentltl_coding.rules import RuleFileError

    if event == "UserPromptSubmit":
        # A subagent's task arrives as its "prompt": that is Codex writing, not the user.
        if not payload.get("agent_id"):
            session.prompt()
            _answered(session)
        return None
    try:
        session.ruleset
    except RuleFileError as exc:
        return _broken_file(event, exc.problems)

    if event in ("SessionStart", "SubagentStart"):
        text = session.start()
        if text is None:
            return None
        out: Dict[str, Any] = {"hookSpecificOutput": {"hookEventName": event,
                                                      "additionalContext": text}}
        if event == "SessionStart":
            out["systemMessage"] = f"AgentLTL: {len(session.ruleset.rules)} rule(s) in force"
        return out
    if event == "Stop":
        verdict = session.finish()
        if verdict.action != "block":
            return None
        return {"decision": "block", "reason": verdict.reason,
                "systemMessage": f"AgentLTL sent Codex back: {_first_line(verdict.reason)}"}

    tool, tool_input = payload.get("tool_name") or "", payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if event == "PreToolUse":
        return _pre(session, payload, tool, tool_input)
    if event == "PostToolUse":
        return _post(session, payload, tool, tool_input)
    return None


# ── PreToolUse ────────────────────────────────────────────────────────────────

def _pre(session: Any, payload: Dict[str, Any], tool: str,
         tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from agentltl_coding.guard import Verdict
    auto = _unattended(payload)
    verdict, notes = Verdict(), []
    for name, args in _calls(tool, tool_input):
        v = session.pre(name, args, auto=auto)
        if v.context:
            notes.append(v.context)
        if _RANK.get(v.action, 0) > _RANK.get(verdict.action, 0):
            verdict = v
        if verdict.action in ("deny", "stop"):
            break
    if verdict.action == "ask" and not auto and _approved(session, tool, tool_input):
        notes = [n for n in notes if n != verdict.context]   # "asked the user": done
        verdict = Verdict()
    spec: Dict[str, Any] = {"hookEventName": "PreToolUse"}
    out: Dict[str, Any] = {"hookSpecificOutput": spec}
    if verdict.action in ("deny", "stop", "ask"):
        reason = verdict.reason
        if verdict.action == "ask":
            if auto:
                reason = (reason.rsplit("\n", 1)[0] + "\nNobody can approve it in an unattended "
                          "run: the call is refused.")
            else:
                reason = _ask_reason(reason)
                _ask(session, tool, tool_input)
        rule = f"rule '{verdict.rule}'" if verdict.rule else "a rule"
        spec["permissionDecision"] = "deny"
        # Codex shows the model "Command blocked by PreToolUse hook: <reason>. Command: ..."
        spec["permissionDecisionReason"] = reason.rstrip().rstrip(".")
        out["systemMessage"] = f"AgentLTL: {rule} refused {_show(tool, tool_input)}"
        if verdict.action == "stop":
            out["systemMessage"] += ("; Codex can explain, but no tool runs until you reply")
    if notes:
        spec["additionalContext"] = "\n".join(notes)
    return out if len(spec) > 1 else None


# ── PostToolUse ───────────────────────────────────────────────────────────────

def _post(session: Any, payload: Dict[str, Any], tool: str,
          tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tool_id = payload.get("tool_use_id") or ""
    output = payload.get("tool_response")
    status = 0
    if tool == "Bash":
        status = 1 if _exit_code(payload.get("transcript_path"), tool_id) else 0
    notes: List[str] = []
    shown: List[str] = []
    for name, args in _calls(tool, tool_input):
        found = session.post(name, args, tool_id, output, status=status)
        if found and found[0] not in shown:
            shown.append(found[0])
            notes.append(found[1])
    if tool == "Bash" and status == 0:
        for path in _printed_files(session, tool_input.get("command") or ""):
            session.post("Read", {"file_path": path}, tool_id, None, status=0)
    if tool == ASK_TOOL:
        _answered(session)
    if not notes:
        return None
    return {"systemMessage": " · ".join(shown),
            "hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": "\n\n".join(notes)}}


def _unattended(payload: Dict[str, Any]) -> bool:
    """Whether nobody can answer: Codex's approval policy is "never" (`codex exec`, --yolo),
    which hooks see as permission_mode "bypassPermissions". AGENTLTL_AUTO=1 says so whatever
    the mode; AGENTLTL_AUTO=0 says someone is there (an interactive session with --yolo)."""
    from agentltl_coding.guard import is_auto
    setting = os.environ.get("AGENTLTL_AUTO")
    return setting == "1" or (setting != "0" and is_auto(payload.get("permission_mode")))


def _calls(tool: str, tool_input: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """The calls rules see for one Codex call: an apply_patch is the Write / Edit / rm calls
    it stands for (all of them, or the patch as is when it can't be read)."""
    if tool == PATCH_TOOL:
        return patch.calls(tool_input.get("command") or tool_input.get("input") or "") \
            or [(tool, tool_input)]
    return [(tool, tool_input)]


def _printed_files(session: Any, command: str) -> List[str]:
    """The files a command line shows the agent: what cat, head, sed -n... were given."""
    from agentltl_coding.guard import translator_for
    from agentltl_coding.pattern import Paths
    try:
        calls = translator_for(session.ruleset, Paths(session.cwd, session.project)) \
            .translate(command)
    except Exception:
        return []
    out: List[str] = []
    for call in calls:
        if call.name not in VIEWERS or call.args.get("in_place"):
            continue
        paths = call.args.get("paths")
        if paths is None:     # a command known only by name: its words that are not options
            paths = [os.path.join(session.cwd, a) for a in call.args.get("argv") or []
                     if isinstance(a, str) and not a.startswith("-")]
        out += [p for p in paths if isinstance(p, str) and p and not p.startswith("-")
                and p not in out]
    return out


def _exit_code(transcript: Optional[str], call_id: str) -> int:
    """A command's exit code, from the rollout Codex writes before running PostToolUse
    (``event_msg`` ``item_completed``, ``item.exit_code``); 0 when it can't be found."""
    if not transcript or not call_id:
        return 0
    try:
        with open(transcript, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 2_000_000))
            lines = fh.read().splitlines()
    except OSError:
        return 0
    needle = call_id.encode()
    for line in reversed(lines):
        if needle not in line or b'"exit_code"' not in line:
            continue
        try:
            item = (json.loads(line).get("payload") or {}).get("item") or {}
        except ValueError:
            continue
        if item.get("id") == call_id and isinstance(item.get("exit_code"), int):
            return item["exit_code"]
    return 0


def _show(tool: str, tool_input: Dict[str, Any]) -> str:
    if tool == PATCH_TOOL:
        what = ", ".join(patch.paths(tool_input.get("command") or ""))
    else:
        what = tool_input.get("command") or tool_input.get("file_path") or ""
    what = " ".join(str(what).split())
    return f"{tool} {what[:80] + ('…' if len(what) > 80 else '')}".strip()


def _first_line(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")[:160]


# ── ask: state kept across hook calls ─────────────────────────────────────────

def _key(tool: str, tool_input: Dict[str, Any]) -> str:
    raw = json.dumps([tool, tool_input], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _ask(session: Any, tool: str, tool_input: Dict[str, Any]) -> None:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        asks = state.setdefault(_ASKS, {})
        asks[_key(tool, tool_input)] = "asked"
        while len(asks) > 20:
            asks.pop(next(iter(asks)))


def _answered(session: Any) -> None:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        if state.get(_ASKS):
            state[_ASKS] = {k: "answered" for k in state[_ASKS]}


def _approved(session: Any, tool: str, tool_input: Dict[str, Any]) -> bool:
    """Whether this exact call was refused for an `ask` rule and the user has been asked since
    (once: the approval is used up)."""
    from agentltl_coding import store
    key = _key(tool, tool_input)
    with store.locked(session.sid) as state:
        asks = state.get(_ASKS) or {}
        if asks.get(key) != "answered":
            return False
        del asks[key]
        # The guard logged this call as an "ask" for `agentltl trace`: it went ahead, approved.
        for d in reversed(state.get("decisions") or []):
            if d.get("action") == "ask":
                d["action"] = "ok"
                break
        return True


def _ask_reason(prompt: str) -> str:
    """The guard's permission prompt, turned into instructions for Codex."""
    lines = [line for line in prompt.splitlines() if not line.endswith("Allow this call anyway?")]
    return "\n".join(lines + [_ASK_TAIL])


# ── trouble ───────────────────────────────────────────────────────────────────

def _broken_file(event: str, problems: list) -> Optional[Dict[str, Any]]:
    """Tell Codex and the user at the start of a session; calls go ahead (no rules)."""
    from agentltl_coding.session import broken
    if event != "SessionStart":
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": broken(problems) + "\nTell the user at "
                                   "the start of your first reply."},
            "systemMessage": "AgentLTL: AGENTLTL.yaml has errors; no rules are enforced"}


def _failure(event: str, exc: Exception) -> Optional[Dict[str, Any]]:
    text = f"AgentLTL guard error ({type(exc).__name__}: {exc})"
    if event == "PreToolUse":
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": text + "; this call was refused because it could not "
                                               "be checked against the rules. Tell the user."},
            "systemMessage": text}
    if event in ("SessionStart", "PostToolUse"):
        return {"hookSpecificOutput": {"hookEventName": event,
                                       "additionalContext": text + ". Tell the user."},
                "systemMessage": text}
    return {"systemMessage": text}


if __name__ == "__main__":
    sys.exit(main())

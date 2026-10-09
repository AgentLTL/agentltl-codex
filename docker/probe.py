#!/usr/bin/env python3
"""A hook that writes each payload it gets to $PROBE_DIR/<n>-<event>.json.

With PROBE_ACT=1 it also acts, to see how Codex takes each answer: it denies a command
containing PROBE_DENY, adds context to every PostToolUse, and blocks the first Stop."""
import json, os, sys, time
payload = json.load(sys.stdin)
event = payload.get("hook_event_name", "unknown")
d = os.environ.get("PROBE_DIR", "/probe")
with open(os.path.join(d, f"{time.time_ns()}-{event}.json"), "w") as fh:
    json.dump({"payload": payload, "env": {k: v for k, v in os.environ.items()
               if "CODEX" in k or "PLUGIN" in k or k in ("PWD", "HOME")}}, fh, indent=1)
if os.environ.get("PROBE_ACT") != "1":
    sys.exit(0)
if event == "PreToolUse" and "PROBE_DENY" in json.dumps(payload.get("tool_input")):
    print(json.dumps({"systemMessage": "probe: denied a marker",
                      "hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": "PROBE says no"}}))
elif event == "PreToolUse" and "PROBE_WARN" in json.dumps(payload.get("tool_input")):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "additionalContext": "PROBE pre note"}}))
elif event == "PostToolUse":
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": "PROBE post note"}}))
elif event == "SessionStart":
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": "PROBE session note"}}))
elif event == "Stop":
    flag = os.path.join(d, "stopped-once")
    if not os.path.exists(flag):
        open(flag, "w").close()
        print(json.dumps({"decision": "block", "reason": "PROBE wants one more step",
                          "systemMessage": "probe: sent back"}))

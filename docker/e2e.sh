#!/usr/bin/env bash
# End to end, no model or account needed: Codex (the version in package.json) in Docker, the
# plugin installed from this checkout, and agentltl-coding's scripted model making the calls in
# e2e/script.json. Checks that the rules in e2e/AGENTLTL.yaml refused what e2e/expected.txt
# says, that the rules were listed to Codex, that `finally` sent Codex back, and that the call
# an `ask` rule held went through once the user approved it.
#
#   docker/e2e.sh          # E2E_OUT=dir keeps the output there (default: a temporary folder)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker build -q -t agentltl-codex "$root/docker" > /dev/null
if [[ -n "${E2E_OUT:-}" ]]; then
    mkdir -p "$E2E_OUT" && out="$(cd "$E2E_OUT" && pwd)"
else
    out="$(mktemp -d)"
fi
chmod 777 "$out"
docker run --rm -v "$root":/src:ro -v "$out":/out agentltl-codex bash /src/docker/e2e/run.sh
echo "Codex: $(cat "$out/version.txt" 2>/dev/null), output in $out"
python3 "$root/vendor/agentltl-coding/e2e/check.py" "$out/trace.txt" "$root/docker/e2e/expected.txt"
python3 - "$out" <<'EOF'
import glob, json, sys
out = sys.argv[1]
with open(sorted(glob.glob(f"{out}/req-*.json"))[-1]) as fh:
    items = json.load(fh)["body"]["input"]  # the last request holds the whole conversation
seen = json.dumps(items)
rm = [i["call_id"] for i in items if i.get("type") == "function_call"
      and "rm -r build" in i.get("arguments", "")]
ran = [i for i in items if i.get("type") == "function_call_output" and i["call_id"] in rm
       and "exited with code 0" in str(i.get("output"))]
missing = [what for what, ok in (
    ("the rules listed to Codex at session start", "AGENTLTL rule(s) on every tool call" in seen),
    ("a `finally` send-back", "commit-before-finishing" in seen and "hook_prompt" in seen),
    ("the approved rm -r build, run after the user's reply", len(rm) == 2 and len(ran) == 1))
    if not ok]
if missing:
    print("FAILED: no", *missing, sep="\n  ")
    sys.exit(1)
print("OK: the rules were listed, Codex was sent back, and the approved call went through.")
EOF

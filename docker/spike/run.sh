#!/usr/bin/env bash
# Capture what a Codex version sends its hooks, for tests/fixtures/payloads: docker/probe.py on
# every event (spike/hooks.json, run with --dangerously-bypass-hook-trust), the scripted model
# making the calls in spike/script.json, one `codex exec`. Payloads land in OUT/probe, the
# requests in OUT/req, the rollouts in OUT/sessions. PROBE_ACT=1 makes the probe answer too
# (deny a PROBE_DENY command, add context, block the first Stop).
#
#   docker build -t agentltl-codex docker/
#   docker run --rm -v "$PWD/docker/spike":/spike:ro \
#     -v "$PWD/vendor/agentltl-coding/e2e/scripted_model.py":/scripted_model.py:ro \
#     -v "$OUT":/out agentltl-codex bash /spike/run.sh
set -u
S=/spike; SCRIPT="${1:-$S/script.json}"; shift || true
export FAKE_KEY=x PROBE_DIR=/out/probe
mkdir -p ~/.codex /out/probe /out/req
cp $S/config.toml $S/hooks.json ~/.codex/
cd /work && printf 'hello\n' > README.md && git add README.md && git commit -qm init
python3 /scripted_model.py "$SCRIPT" --log /out/req &
sleep 1
timeout 300 codex exec --json --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox \
   --dangerously-bypass-hook-trust "$@" "do the scripted steps" > /out/codex.jsonl 2> /out/codex-stderr.txt
echo "exit $?" >> /out/codex-stderr.txt
cp -r ~/.codex/sessions /out/ 2>/dev/null
git -C /work log --format='%H%n%B' > /out/gitlog.txt

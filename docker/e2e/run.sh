#!/usr/bin/env bash
# Runs inside the agentltl-codex image (see ../e2e.sh): installs the plugin from /src as a user
# would (a local marketplace, `codex plugin add`, `agentltl install`), starts the scripted model,
# runs one `codex exec` session in /work with e2e/AGENTLTL.yaml, resumes it with the user's
# approval of the `ask`, and leaves what happened in /out.
#
# The hooks run only because `agentltl install` trusted them: no --dangerously-bypass-hook-trust.
set -u
here=/src/docker/e2e
export FAKE_KEY=x
mkdir -p ~/.codex /out
cp "$here/config.toml" ~/.codex/
cp -r /src /tmp/agentltl-codex && rm -rf /tmp/agentltl-codex/.venv
cd /work && printf 'hello\n' > README.md && git add README.md && git commit -qm init
cp "$here/AGENTLTL.yaml" /work/AGENTLTL.yaml
{
    codex plugin marketplace add /tmp/agentltl-codex
    codex plugin add agentltl@agentltl
    plugin="$(ls -td ~/.codex/plugins/cache/agentltl/agentltl/*/ | head -1)"
    "${plugin}bin/agentltl" install --no-cli
} > /out/install.txt 2>&1
codex --version > /out/version.txt 2>&1
python3 /src/vendor/agentltl-coding/e2e/scripted_model.py "$here/script.json" --log /out &
sleep 1
# `codex exec` never asks for approval, so its hooks say nobody can answer; here the second
# `codex exec` is the user answering: AGENTLTL_AUTO=0 lets `ask` rules ask.
export AGENTLTL_AUTO=0
run=(--json --dangerously-bypass-approvals-and-sandbox)
timeout 300 codex exec --skip-git-repo-check "${run[@]}" "do the scripted steps" \
    > /out/codex.jsonl 2> /out/codex-stderr.txt
echo "exit $?" >> /out/codex-stderr.txt
timeout 300 codex exec resume --last "${run[@]}" "yes, go ahead" \
    > /out/codex-resume.jsonl 2>> /out/codex-stderr.txt
echo "exit $?" >> /out/codex-stderr.txt
"${plugin}bin/agentltl" trace > /out/trace.txt 2>&1
git -C /work log --format='%h %s%n%b' > /out/git-log.txt

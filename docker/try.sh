#!/usr/bin/env bash
# Try the plugin yourself: an interactive shell in Docker with Codex on your own model (.env,
# see .env.example), the plugin installed from GitHub as a user would, and a scratch repository
# in /work with a few rules. Type `codex` to start; `agentltl trace` shows what was refused.
#
#   docker/try.sh             # the plugin from GitHub
#   docker/try.sh --local     # the plugin from this checkout
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$root/.env" ]] || { echo "No $root/.env: copy .env.example and fill it in." >&2; exit 1; }
docker build -q -t agentltl-codex "$root/docker" > /dev/null
source="AgentLTL/agentltl-codex"
mounts=()
if [[ "${1:-}" == "--local" ]]; then
    source="/tmp/agentltl-codex"
    mounts=(-v "$root":/src:ro)
fi
docker run --rm -it --network host --env-file "$root/.env" -e SOURCE="$source" "${mounts[@]}" \
    agentltl-codex bash -c '
set -e
if [[ "$SOURCE" == /tmp/* ]]; then cp -r /src "$SOURCE" && rm -rf "$SOURCE/.venv" "$SOURCE/.env"; fi
echo "Installing AgentLTL for Codex from $SOURCE..."
codex plugin marketplace add "$SOURCE" > /dev/null
codex plugin add agentltl@agentltl > /dev/null
"$(ls -td ~/.codex/plugins/cache/agentltl/agentltl/*/ | head -1)"bin/agentltl install
cd /work
printf "hello\n" > README.md && mkdir -p build && touch build/x
git add README.md && git commit -qm init
cat > AGENTLTL.yaml <<YAML
use: [read-before-overwrite, no-force-push, no-codex-coauthor]
rules:
  - {id: no-sudo, never: sudo, why: Nothing here needs root.}
  - {id: ask-before-rm-r, never: {tool: rm, with: {recursive: true}}, mode: ask}
  - id: commit-before-finishing
    finally: {call: {tool: git_commit, succeeded: true}, since: [Write, Edit]}
YAML
export PATH="$HOME/.local/bin:$PATH"
echo
echo "Ready: /work has AGENTLTL.yaml. Type codex to start; agentltl trace shows what was refused."
exec bash'

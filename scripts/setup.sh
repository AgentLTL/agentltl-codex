#!/usr/bin/env bash
# Create the plugin's virtualenv with its dependencies: agentltl, cli-to-tools,
# agentltl-coding, pyyaml.
#
#   scripts/setup.sh            # venv in the plugin data directory, venv-<pins checksum>
#   scripts/setup.sh --dev      # <repo>/.venv, editable, with pytest and ruff
#
# The guard's own code is not installed: the hooks run it from the plugin directory, so a
# plugin update (a new directory) takes effect without reinstalling. A new venv is only
# needed when vendor.lock changes; scripts/env.sh names it after the pins.
#
# Dependencies come from the vendor/ submodules when they are checked out, otherwise from
# GitHub at the commits pinned in vendor.lock.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=env.sh
source "$root/scripts/env.sh"
if [[ "${1:-}" == "--dev" ]]; then
    venv="${AGENTLTL_CODEX_VENV:-$root/.venv}"
else
    venv="$(env_venv)"
fi

python="${PYTHON:-python3}"
[[ -x "$venv/bin/python" ]] || "$python" -m venv "$venv"
pip="$venv/bin/pip"
"$pip" install -q --upgrade pip

# Editable installs only for development: an installed plugin's directory is replaced on
# update, so it must get real copies.
editable=""
[[ "${1:-}" == "--dev" ]] && editable="-e"

while read -r name url commit; do
    [[ -z "$name" || "$name" == \#* ]] && continue
    case "$name" in agentltl) dir=AgentLTL ;; *) dir="$name" ;; esac
    if [[ -f "$root/vendor/$dir/pyproject.toml" ]]; then
        "$pip" install -q $editable "$root/vendor/$dir"
    else
        "$pip" install -q "$name @ git+$url@$commit"
    fi
done < "$root/vendor.lock"
"$pip" install -q "pyyaml>=6.0"

if [[ "${1:-}" == "--dev" ]]; then
    "$pip" install -q -e "$root[dev]"
fi
cp "$root/vendor.lock" "$venv/vendor.lock"
echo "AgentLTL installed in $venv"

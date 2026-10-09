# Sourced by hooks/run, bin/agentltl and scripts/setup.sh: where the plugin's Python lives.
#
# Each set of dependency pins (vendor.lock) gets its own virtualenv, venv-<checksum>, in the
# plugin's data directory: $PLUGIN_DATA in a hook, else
# ${CODEX_HOME:-~/.codex}/plugins/data/agentltl-agentltl (AGENTLTL_DATA_DIR overrides both). An update that moves a pin builds a new one on its first use; a session
# still running the previous version keeps the old one, so the two never rebuild over each
# other. Environments unused for 14 days are removed.
#
# A checkout with its own .venv (scripts/setup.sh --dev) uses that instead. Expects $root
# (the plugin directory).

env_data_dir() {
    echo "${AGENTLTL_DATA_DIR:-${PLUGIN_DATA:-${CODEX_HOME:-$HOME/.codex}/plugins/data/agentltl-agentltl}}"
}

env_venv() {
    if [[ -n "${AGENTLTL_CODEX_VENV:-}" ]]; then echo "$AGENTLTL_CODEX_VENV"; return; fi
    echo "$(env_data_dir)/venv-$(cksum < "$root/vendor.lock" | cut -d' ' -f1)"
}

env_python() {
    # The Python to run the guard with, or nothing when it is not built yet.
    local c
    for c in "${AGENTLTL_CODEX_PYTHON:-}" "$root/.venv/bin/python" "$(env_venv)/bin/python"; do
        if [[ -n "$c" && -x "$c" ]]; then echo "$c"; return 0; fi
    done
    return 1
}

env_build() {
    # Build the virtualenv for these pins unless it exists; one build at a time, since
    # parallel tool calls each run a hook. mkdir is an atomic lock that also works on macOS.
    local venv lock waited=0
    venv="$(env_venv)"
    lock="$(dirname "$venv")/.setup.lock"
    mkdir -p "$(dirname "$lock")"
    while ! mkdir "$lock" 2>/dev/null; do
        sleep 1; waited=$((waited + 1))
        if (( waited > 90 )); then rm -rf "$lock"; fi   # a crashed build left it behind
    done
    if [[ ! -x "$venv/bin/python" ]]; then
        AGENTLTL_CODEX_VENV="$venv" "$root/scripts/setup.sh" >&2
    fi
    rmdir "$lock" 2>/dev/null
}

env_touch_and_prune() {
    # Mark this environment as in use; remove the plugin's other environments unused for
    # 14 days.
    local data venv stamp
    [[ -n "${AGENTLTL_CODEX_VENV:-}" ]] && return 0
    data="$(env_data_dir)"
    venv="$(env_venv)"
    [[ -f "$venv/vendor.lock" ]] && touch "$venv/vendor.lock"
    for stamp in "$data"/venv-*/vendor.lock; do
        [[ -f "$stamp" && "$(dirname "$stamp")" != "$venv" ]] || continue
        if [[ -n "$(find "$stamp" -mtime +14 2>/dev/null)" ]]; then rm -rf "$(dirname "$stamp")"; fi
    done
    return 0
}

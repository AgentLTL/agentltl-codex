#!/usr/bin/env bash
# Point Codex at the OpenAI-compatible model in the environment (VLLM_*, see .env.example; the
# server must serve the Responses API, /v1/responses), then run the command.
set -euo pipefail
home="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$home"
if [[ -n "${VLLM_BASE_URL:-}" && ! -f "$home/config.toml" ]]; then
    base="${VLLM_BASE_URL%/}"
    [[ "$base" == */v1 ]] || base="$base/v1"
    # Codex gives a model it doesn't know fewer tools (no apply_patch): describe this one as
    # Codex's own gpt-5.5, under its name, minus what vLLM's Responses API rejects ("unknown
    # tool type"): tool_search, and the namespace tools of subagents (features.multi_agent,
    # below).
    codex debug models --bundled | python3 -c '
import json, sys
model, window = sys.argv[1], int(sys.argv[2])
entry = next(m for m in json.load(sys.stdin)["models"] if m["slug"] == "gpt-5.5")
entry.update(slug=model, display_name=model, context_window=window, max_context_window=window,
             auto_compact_token_limit=int(window * 0.8), supports_search_tool=False)
json.dump({"models": [entry]}, sys.stdout)' "${VLLM_MODEL:-qwen3.8-27b}" "${VLLM_MAX_CONTEXT:-65536}" \
        > "$home/models.json"
    cat > "$home/config.toml" <<TOML
model = "${VLLM_MODEL:-qwen3.8-27b}"
model_provider = "vllm"
model_catalog_json = "$home/models.json"
check_for_update_on_startup = false

[model_providers.vllm]
name = "vLLM"
base_url = "${base}"
env_key = "VLLM_API_KEY"
wire_api = "responses"

[features]
multi_agent = false

[analytics]
enabled = false

[feedback]
enabled = false

[projects."/work"]
trust_level = "trusted"
TOML
fi
export VLLM_API_KEY="${VLLM_API_KEY:-none}"
exec "$@"

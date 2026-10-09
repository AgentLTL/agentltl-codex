#!/usr/bin/env bash
# Point Codex at the OpenAI-compatible model in the environment (VLLM_*, see .env.example; the
# server must serve the Responses API, /v1/responses), then run the command.
set -euo pipefail
home="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$home"
if [[ -n "${VLLM_BASE_URL:-}" && ! -f "$home/config.toml" ]]; then
    base="${VLLM_BASE_URL%/}"
    [[ "$base" == */v1 ]] || base="$base/v1"
    cat > "$home/config.toml" <<TOML
model = "${VLLM_MODEL:-qwen3.8-27b}"
model_provider = "vllm"
check_for_update_on_startup = false

[model_providers.vllm]
name = "vLLM"
base_url = "${base}"
env_key = "VLLM_API_KEY"
wire_api = "responses"

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

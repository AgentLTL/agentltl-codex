# OpenAI Codex CLI with Python, for trying the AgentLTL plugin end to end (see the README,
# "Development"):
#
#   docker/e2e.sh                # a scripted model, no account needed
#   docker/live.sh "a task"      # your OpenAI-compatible model (Responses API), from .env
#
# The Codex version is pinned in package.json (Dependabot proposes each new release). /work is a
# scratch git repository; the entrypoint points Codex at the model in VLLM_*.
FROM node:22-bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates jq procps \
 && rm -rf /var/lib/apt/lists/*
COPY package.json /opt/agentltl/package.json
RUN npm install -g "@openai/codex@$(jq -r '.dependencies["@openai/codex"]' /opt/agentltl/package.json)"
RUN useradd -m dev && mkdir /work /probe && chown dev /work /probe
USER dev
ENV PATH="/home/dev/.local/bin:${PATH}"
RUN git config --global user.name dev && git config --global user.email dev@example.com \
 && git config --global init.defaultBranch main && git -C /work init -q
COPY --chown=dev entrypoint.sh probe.py /opt/agentltl/
WORKDIR /work
ENTRYPOINT ["/opt/agentltl/entrypoint.sh"]
CMD ["bash"]

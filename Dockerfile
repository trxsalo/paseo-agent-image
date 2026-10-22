# Inherit Paseo's official multi-architecture image, pinned to the digest
# verified on 2026-10-21. Keep the base entrypoint and final user behavior.
FROM ghcr.io/getpaseo/paseo@sha256:0d17dd75a51c591907a4bbcd505013102048246a0cd6e824de3b38a6057ff862

USER root
RUN npm install --global @openai/codex@0.163.0 @anthropic-ai/claude-code@2.1.306

# Persistent /home/paseo volumes hide build-time ownership fixes. Repair CLI
# config ownership at startup, then delegate to Paseo's original Tini entrypoint.
COPY --chmod=755 docker/paseo-agent-config-permissions.sh /usr/local/bin/paseo-agent-config-permissions
ENTRYPOINT ["/usr/local/bin/paseo-agent-config-permissions"]

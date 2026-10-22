# Inherit Paseo's official multi-architecture image, pinned to the digest
# verified on 2026-10-21. Keep the base entrypoint and final user behavior.
FROM ghcr.io/getpaseo/paseo@sha256:0d17dd75a51c591907a4bbcd505013102048246a0cd6e824de3b38a6057ff862

USER root

ARG CODEX_VERSION=0.163.0
ARG CLAUDE_CODE_VERSION=2.1.306
ARG COPILOT_VERSION=1.0.102
ARG OPENCODE_VERSION=2.1.2
ARG PI_VERSION=1.4.0
ARG OMP_VERSION=18.12.6
ARG ANTIGRAVITY_VERSION=1.4.4
ARG ANTIGRAVITY_BUILD_ID=4783783166214144
ARG MUSE_LAUNCHER_SHA256=c6db294799a190ca380da274beb3b9c0e160e0da9681a3d364ce8b0e5fa3a4bc

RUN npm install --global \
      "@openai/codex@${CODEX_VERSION}" \
      "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
      "@github/copilot@${COPILOT_VERSION}" \
      "@opencode/cli@${OPENCODE_VERSION}" \
      "@earendil-works/pi-coding-agent@${PI_VERSION}"

# Install native, architecture-specific provider CLIs from checksum-verified releases.
ARG TARGETARCH
RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) \
        omp_asset=omp-linux-x64; \
        omp_sha256=85d9daf3a05fc76e8cd425ae1904eb576af8d21cc85fcf4690742626e07ccfa4; \
        agy_path=linux-x64/cli_linux_x64.tar.gz; \
        agy_sha512=7ce149d350344c1046c7b59b6659bcc5d659f351bf3a07c6c085887d93427ceb89d927752e4ccd0844b53ffb91d33d6a49f72835ceb276c7cffdd13cfb8023b8 ;; \
      arm64) \
        omp_asset=omp-linux-arm64; \
        omp_sha256=eee8e586274cef2e725c218b2b28b48ca9965d46dd58f60998cb347eca4ad0cf; \
        agy_path=linux-arm/cli_linux_arm64.tar.gz; \
        agy_sha512=7bfc4f7e5e2dda4cd0c536c72cf9725c2918a038028ad11fa4f7f5e57db77e9ff7d6b9beca05cd85618b77dd3e77de64b63629d33e5779f29111390dc53c7aaf ;; \
      *) echo "Unsupported target architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl --fail --silent --show-error --location --retry 3 --proto '=https' --proto-redir '=https' --tlsv1.2 \
      "https://github.com/can1357/oh-my-pi/releases/download/v${OMP_VERSION}/${omp_asset}" \
      --output /tmp/omp; \
    printf '%s  %s\n' "$omp_sha256" /tmp/omp | sha256sum --check -; \
    install -m 0755 /tmp/omp /usr/local/bin/omp; \
    curl --fail --silent --show-error --location --retry 3 --proto '=https' --proto-redir '=https' --tlsv1.2 \
      "https://storage.googleapis.com/antigravity-public/antigravity-cli/${ANTIGRAVITY_VERSION}-${ANTIGRAVITY_BUILD_ID}/${agy_path}" \
      --output /tmp/agy.tar.gz; \
    printf '%s  %s\n' "$agy_sha512" /tmp/agy.tar.gz | sha512sum --check -; \
    mkdir -p /tmp/agy; \
    tar -xzf /tmp/agy.tar.gz -C /tmp/agy antigravity; \
    install -m 0755 /tmp/agy/antigravity /usr/local/bin/agy; \
    rm -rf /tmp/omp /tmp/agy.tar.gz /tmp/agy

# Install Meta's hash-pinned launcher; a small wrapper copies it into the
# service user's writable persistent home so its binary/update state can live
# there, rather than baking a several-hundred-megabyte binary into each image.
RUN set -eux; \
    mkdir -p /usr/local/share; \
    curl --fail --silent --show-error --location --max-redirs 3 --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://api.meta.ai/muse-launcher.sh --output /usr/local/share/paseo-muse-launcher.sh; \
    printf '%s  %s\n' "$MUSE_LAUNCHER_SHA256" /usr/local/share/paseo-muse-launcher.sh | sha256sum --check -; \
    chmod 0644 /usr/local/share/paseo-muse-launcher.sh; \
    bash -n /usr/local/share/paseo-muse-launcher.sh

# Persistent /home/paseo volumes hide build-time ownership fixes. Repair all
# provider auth/config state at startup, then delegate to Paseo's original init.
COPY --chmod=755 docker/paseo-agent-config-permissions.sh /usr/local/bin/paseo-agent-config-permissions
COPY --chmod=755 docker/paseo-muse-launcher.sh /usr/local/bin/muse
COPY --chmod=755 tests/smoke-provider-binaries.sh /usr/local/bin/paseo-provider-smoke
RUN set -eux; \
    mkdir -p /tmp/paseo-provider-smoke; \
    HOME=/tmp/paseo-provider-smoke \
      CODEX_HOME=/tmp/paseo-provider-smoke/.codex \
      CLAUDE_CONFIG_DIR=/tmp/paseo-provider-smoke/.claude \
      XDG_CONFIG_HOME=/tmp/paseo-provider-smoke/.config \
      XDG_DATA_HOME=/tmp/paseo-provider-smoke/.local/share \
      /usr/local/bin/paseo-provider-smoke; \
    rm -rf /tmp/paseo-provider-smoke

ENTRYPOINT ["/usr/local/bin/paseo-agent-config-permissions"]

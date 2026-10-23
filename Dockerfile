# Inherit Paseo's official multi-architecture image, pinned to the digest
# verified on 2026-10-21. Keep the base entrypoint and final user behavior.
FROM ghcr.io/getpaseo/paseo@sha256:0d17dd75a51c591907a4bbcd505013102048246a0cd6e824de3b38a6057ff862 AS runtime-base

USER root

ARG OMP_VERSION=18.12.6
ARG ANTIGRAVITY_VERSION=1.4.4
ARG ANTIGRAVITY_BUILD_ID=4783783166214144
ARG MUSE_LAUNCHER_SHA256=c6db294799a190ca380da274beb3b9c0e160e0da9681a3d364ce8b0e5fa3a4bc

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

ARG GH_VERSION=2.103.0
RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) gh_sha256=fdd768eb70f6409f80fcfa9f3a1c0adf0fc98d827ab3ce0bed2ac22762c5d786 ;; \
      arm64) gh_sha256=7f322df34e624d14f5ec0c4acb121fd6dfa14392fdbbd1066aa8e0a05ac3721e ;; \
      *) echo "Unsupported target architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    gh_dir="gh_${GH_VERSION}_linux_${TARGETARCH}"; \
    curl --fail --silent --show-error --location --retry 3 --proto '=https' --proto-redir '=https' --tlsv1.2 \
      "https://github.com/cli/cli/releases/download/v${GH_VERSION}/${gh_dir}.tar.gz" \
      --output /tmp/gh.tar.gz; \
    printf '%s  %s\n' "$gh_sha256" /tmp/gh.tar.gz | sha256sum --check -; \
    mkdir -p /tmp/gh /usr/local/share/licenses/gh; \
    tar -xzf /tmp/gh.tar.gz -C /tmp/gh "$gh_dir/bin/gh" "$gh_dir/LICENSE"; \
    install -m 0755 "/tmp/gh/$gh_dir/bin/gh" /usr/local/bin/gh; \
    install -m 0644 "/tmp/gh/$gh_dir/LICENSE" /usr/local/share/licenses/gh/LICENSE; \
    rm -rf /tmp/gh.tar.gz /tmp/gh

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

# ACP catalog snapshot: isolated npm/Python environments and native Linux agents.
# Pin the catalog in source; image builds never fetch a moving registry index.
ENV UV_PYTHON_INSTALL_DIR=/opt/paseo-acp/python \
    UV_CACHE_DIR=/tmp/paseo-uv-cache \
    UV_LINK_MODE=copy
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      python3 python3-venv build-essential pkg-config libdbus-1-dev \
      libsecret-1-0 libgomp1 libatomic1 unzip; \
    rm -rf /var/lib/apt/lists/*; \
    python3 -m venv /opt/paseo-acp/bootstrap
COPY docker/dependency-locks/python/uv.txt /tmp/paseo-uv.lock
RUN set -eux; \
    /opt/paseo-acp/bootstrap/bin/pip install --no-cache-dir --only-binary=:all: \
      --require-hashes -r /tmp/paseo-uv.lock; \
    ln -s /opt/paseo-acp/bootstrap/bin/uv /usr/local/bin/uv; \
    ln -s /opt/paseo-acp/bootstrap/bin/uvx /usr/local/bin/uvx; \
    mkdir -p /opt/paseo-acp/bin; \
    chown 1000:1000 /opt/paseo-acp /opt/paseo-acp/bin
COPY docker/acp-catalog.lock.json /usr/local/share/paseo-acp-catalog.json
COPY docker/native-clis.lock.json /usr/local/share/paseo-native-clis.json
COPY docker/dependency-locks/ /usr/local/share/paseo-dependency-locks/
COPY --chmod=755 docker/paseo-acp.py /usr/local/bin/paseo-acp

# Third-party install scripts run as Paseo in a disposable stage, without runtime
# credentials. The next stage copies only artifacts, owned by root, not home/cache.
FROM runtime-base AS agents-build
ARG TARGETARCH
ARG ACP_AGENTS=all
ENV PASEO_ACP_BIN=/opt/paseo-acp/bin \
    NPM_CONFIG_CACHE=/tmp/paseo-npm-cache \
    PATH=$PATH:/opt/paseo-acp/bin
USER paseo
RUN --mount=type=cache,id=paseo-npm-${TARGETARCH},target=/tmp/paseo-npm-cache,uid=1000,gid=1000,sharing=locked \
    /usr/local/bin/paseo-acp install-native
RUN --mount=type=cache,id=paseo-npm-${TARGETARCH},target=/tmp/paseo-npm-cache,uid=1000,gid=1000,sharing=locked \
    --mount=type=cache,id=paseo-uv-${TARGETARCH},target=/tmp/paseo-uv-cache,uid=1000,gid=1000,sharing=locked \
    set -eux; \
    if [ "$ACP_AGENTS" = all ]; then \
      /usr/local/bin/paseo-acp install --arch "$TARGETARCH"; \
    else \
      /usr/local/bin/paseo-acp install --arch "$TARGETARCH" --only "$ACP_AGENTS"; \
    fi; \
    /usr/local/bin/paseo-acp check

FROM runtime-base AS final
COPY --from=agents-build --chown=0:0 /opt/paseo-acp/ /opt/paseo-acp/
RUN set -eux; \
    test ! -L /opt/paseo-acp; \
    test ! -L /opt/paseo-acp/bin; \
    /usr/bin/chown -h 0:0 /opt/paseo-acp /opt/paseo-acp/bin; \
    /usr/bin/find /opt/paseo-acp -type d ! -perm 0755 -exec /usr/bin/chmod 0755 {} +; \
    /usr/bin/find /opt/paseo-acp -type f -perm /111 ! -perm 0755 -exec /usr/bin/chmod 0755 {} +; \
    /usr/bin/find /opt/paseo-acp -type f ! -perm /111 ! -perm 0644 -exec /usr/bin/chmod 0644 {} +
ENV PATH=$PATH:/opt/paseo-acp/bin

# Persistent /home/paseo volumes hide build-time ownership fixes. Repair all
# provider auth/config state at startup, then delegate to Paseo's original init.
COPY --chmod=755 docker/paseo-agent-config-permissions.sh /usr/local/bin/paseo-agent-config-permissions
COPY --chmod=644 docker/paseo-repair-permissions.py /usr/local/libexec/paseo-repair-permissions.py
COPY --chmod=755 docker/paseo-muse-launcher.sh /usr/local/bin/muse
COPY --chmod=755 tests/smoke-provider-binaries.sh /usr/local/bin/paseo-provider-smoke
COPY --chmod=755 tests/verify_service_identity.sh /tmp/paseo-verify-identity.sh
RUN set -eux; \
    /usr/bin/ln -s /etc /home/paseo/.permission-boundary-test; \
    CODEX_HOME=/home/paseo/.permission-boundary-test TINI_SUBREAPER=1 \
      /usr/local/bin/paseo-agent-config-permissions /bin/sh /tmp/paseo-verify-identity.sh; \
    /usr/bin/rm /home/paseo/.permission-boundary-test /tmp/paseo-verify-identity.sh
RUN set -eux; \
    /usr/bin/install -d -m 700 -o 1000 -g 1000 /tmp/paseo-provider-smoke; \
    /usr/sbin/gosu paseo /usr/bin/env HOME=/tmp/paseo-provider-smoke \
      CODEX_HOME=/tmp/paseo-provider-smoke/.codex \
      CLAUDE_CONFIG_DIR=/tmp/paseo-provider-smoke/.claude \
      XDG_CONFIG_HOME=/tmp/paseo-provider-smoke/.config \
      XDG_DATA_HOME=/tmp/paseo-provider-smoke/.local/share \
      /usr/local/bin/paseo-provider-smoke; \
    /usr/bin/rm -rf /tmp/paseo-provider-smoke

ENTRYPOINT ["/usr/local/bin/paseo-agent-config-permissions"]

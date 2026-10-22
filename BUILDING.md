# Paseo image with screenshot provider CLIs

This derived image keeps the official Paseo multi-architecture base pinned to the digest verified on 2026-10-21. It installs Codex CLI `0.163.0`, Claude Code `2.1.306`, GitHub Copilot CLI `1.0.102`, OpenCode `2.1.2`, Pi `1.4.0`, Oh My Pi `18.12.6`, and Antigravity CLI `1.4.4`. Muse Code's official launcher is pinned by SHA-256; a small wrapper stages it in the service user's writable `/home/paseo/.local/bin` on first use, where the launcher downloads the current stable Muse binary. This avoids adding several hundred megabytes to each image architecture.

The image does not enable providers in Paseo or include any provider credentials. Complete each provider's own interactive authentication as the `paseo` user. The Oh My Pi toggle remains a Paseo setting and is not changed by installing its CLI. Antigravity can run with broad workspace/command permissions in Paseo; enable it only if that access is intended.

At startup, the wrapper repairs mismatched ownership anywhere below the persistent `/home/paseo` home to UID/GID `1000:1000`, without following symlinks or crossing mounts. It also retains private modes for Codex's config directory, `tmp`, and `config.toml`, plus Claude's config directory and `.claude.json`, then delegates to Paseo's original Tini entrypoint. This addresses provider state created from a root shell while preserving all existing files and volumes.

## GitHub Actions workflow

The repository includes a manually triggered multi-architecture build workflow. Before the first run, add a Docker Hub access token with read/write permission to this private GitHub repository as the Actions secret `DOCKERHUB_TOKEN`. Add it directly in GitHub Settings → Secrets and variables → Actions; never paste it into chat or commit it. Then run **Build and publish Paseo CLI image** from the Actions tab. The image repository `trxsalo/paseo-agent-clis` is currently public, so anyone can pull it. Keep that visibility intentional; if changing it, update the Dokploy pull-auth configuration as well.

The workflow validates the startup wrapper and provider smoke checks, runs the ownership test, then builds and pushes `linux/amd64` and `linux/arm64`.

## Build and publish locally

If using another CI runner or local Buildx instead, authenticate to Docker Hub through its credential prompt/secret store and run:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag docker.io/trxsalo/paseo-agent-clis:2026-10-22-providers \
  --push .
```

The Docker Hub repository must exist and allow pushes. Keep it private unless public distribution is intentional. Do not put credentials in this file or in command arguments; authenticate interactively or through the runner's secret store.

## Deploy in Dokploy

After the push is confirmed and deployment is approved, change only the Paseo Compose `image:` reference to `docker.io/trxsalo/paseo-agent-clis:2026-10-22-providers`, then redeploy with fresh volumes disabled. Preserve the existing `/home/paseo` and `/workspace` volumes.

## Authenticate inside the running container

Run each provider CLI from the Dokploy host/container console as the `paseo` user and complete its own interactive sign-in. The installed command names are `codex`, `claude`, `copilot`, `opencode`, `pi`, `omp`, `agy`, and `muse`. Do not copy host authentication directories into the container or put credentials in the image, Compose, chat, or logs.

For example, verify Codex and Claude discovery with:

```bash
docker exec -it --user paseo paseo paseo provider diagnostic codex --json
docker exec -it --user paseo paseo paseo provider diagnostic claude
```

The persistent `/home/paseo` volume keeps each CLI's configuration and authentication across redeploys. A successful image build proves the commands are installed; provider login and a fresh Paseo session are still required to verify account access.

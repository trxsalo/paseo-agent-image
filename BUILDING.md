# Paseo image with Codex CLI and Claude Code

Dockerfile is pinned to the official Paseo multi-architecture manifest digest verified 2026-10-21, with Codex CLI `0.163.0` and Claude Code `2.1.306`. A startup wrapper repairs ownership of the persistent Codex, Claude, XDG, Gemini, Aider, and OpenCode config paths to UID/GID `1000:1000`; it applies private modes to Codex's directory, `tmp`, and `config.toml`, plus Claude's config directory and `.claude.json`. It then delegates to the pinned image's original Tini/Paseo entrypoint. This is necessary because `/home/paseo` is a persistent volume and masks ownership changes made only during image build.

## GitHub Actions workflow

The repository includes a manually triggered multi-architecture build workflow. Before the first run, add a Docker Hub access token with read/write permission to this private GitHub repository as the Actions secret `DOCKERHUB_TOKEN`. Add it directly in GitHub Settings → Secrets and variables → Actions; never paste it into chat or commit it. Then run **Build and publish Paseo CLI image** from the Actions tab. The image repository `trxsalo/paseo-agent-clis` is currently public, so anyone can pull it. Keep that visibility intentional; if changing it, update the Dokploy pull-auth configuration as well.

## Build and publish locally

If using another CI runner or local Buildx instead, authenticate to Docker Hub through its credential prompt/secret store and run:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag docker.io/trxsalo/paseo-agent-clis:2026-10-22 \
  --push .
```

The Docker Hub repository must exist and allow pushes. Keep it private unless public distribution is intentional. Do not put credentials in this file or in command arguments; authenticate interactively or through the runner's secret store.

## Deploy in Dokploy

After the push is confirmed, change only the Paseo Compose `image:` reference to `docker.io/trxsalo/paseo-agent-clis:2026-10-22`, then redeploy with fresh volumes disabled. Preserve the existing `/home/paseo` and `/workspace` volumes.

## Persistent AI CLI permissions

The startup wrapper covers the installed Codex and Claude CLIs and common user-level config locations for other agent CLIs. It repairs ownership before Paseo drops privileges, including files previously created from a root shell. Log in and run provider CLIs as the `paseo` user—not root—so new credentials remain accessible to the app; the commands below show the Docker-host form.

## Authenticate inside the running container

Run these from the Dokploy host/its container console as the `paseo` user, one at a time, and complete each CLI's interactive login:

```bash
docker exec -it --user paseo paseo codex
docker exec -it --user paseo paseo claude
```

Then verify provider detection:

```bash
docker exec -it --user paseo paseo paseo provider diagnostic codex --json
docker exec -it --user paseo paseo paseo provider diagnostic claude
```

The persistent `/home/paseo` volume keeps each CLI's own configuration. Do not copy authentication files from a laptop into the container unless you deliberately choose that trust boundary.

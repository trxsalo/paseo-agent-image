# Paseo image with Codex CLI and Claude Code

Dockerfile is pinned to the official Paseo multi-architecture manifest digest verified 2026-10-21, with Codex CLI `0.163.0` and Claude Code `2.1.306`.

## GitHub Actions workflow

The repository includes a manually triggered multi-architecture build workflow. Before the first run, add a Docker Hub access token with read/write permission to this private GitHub repository as the Actions secret `DOCKERHUB_TOKEN`. Add it directly in GitHub Settings → Secrets and variables → Actions; never paste it into chat or commit it. Then run **Build and publish Paseo CLI image** from the Actions tab. The image repository `trxsalo/paseo-agent-clis` is currently public, so anyone can pull it. Keep that visibility intentional; if changing it, update the Dokploy pull-auth configuration as well.

## Build and publish locally

If using another CI runner or local Buildx instead, authenticate to Docker Hub through its credential prompt/secret store and run:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag docker.io/trxsalo/paseo-agent-clis:2026-10-21 \
  --push .
```

The Docker Hub repository must exist and allow pushes. Keep it private unless public distribution is intentional. Do not put credentials in this file or in command arguments; authenticate interactively or through the runner's secret store.

## Deploy in Dokploy

After the push is confirmed, change only the Paseo Compose `image:` reference to `docker.io/trxsalo/paseo-agent-clis:2026-10-21`, then redeploy with fresh volumes disabled. Preserve the existing `/home/paseo` and `/workspace` volumes.

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

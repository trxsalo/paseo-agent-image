# Paseo image with native provider CLIs and GitHub CLI

This derived image keeps the official Paseo multi-architecture base pinned to the digest verified on 2026-10-21. It installs Codex CLI `0.163.0`, Claude Code `2.1.306`, GitHub Copilot CLI `1.0.102`, OpenCode `2.1.2`, Pi `1.4.0`, Oh My Pi `18.12.6`, Antigravity CLI `1.4.4`, and GitHub CLI `2.103.0`. Muse Code's official launcher is pinned by SHA-256; a small wrapper stages it in the service user's writable `/home/paseo/.local/bin` on first use, where the launcher downloads the current stable Muse binary. This avoids adding several hundred megabytes to each image architecture.

The image also installs the Linux-compatible agents from the reviewed ACP catalog
snapshot in `docker/acp-catalog.lock.json`, including Hermes `v0.22.4` with its ACP
extra. See [ACP providers](docs/acp-providers.md) for the inventory, exclusions,
authentication and `paseo-acp configure` commands. The default build installs entries
with a compatible distribution, reviewed SHA-256 and complete dependency locks;
unverified entries are reported as unavailable. `--build-arg ACP_AGENTS=hermes,gemini` builds a selected subset.
Native agents and GitHub CLI remain installed in either case.

Native and ACP npm dependencies use committed complete lockfiles. Python tools
use hashed requirements. Hermes uses its upstream frozen runtime lock plus a
hashed build-tool lock, with automatic build dependency installation disabled.
Third-party npm
and Python install/build scripts run as `paseo` in a disposable build stage.
The final image copies artifacts as root-owned files and removes group/world
write and setuid/setgid permissions. Runtime credentials and build caches are
not copied from the builder. Version changes require regenerating and reviewing
the dependency locks, not overriding Docker build version arguments.

Native npm CLIs and ACP agents install in separate build layers. BuildKit caches
npm and uv downloads per architecture, outside the final image. Retry a failed
build with the same builder and without `--no-cache` to retain completed layers
and reuse downloaded packages; package integrity checks still apply.

Before installing the native CLIs or ACP agents, `paseo-acp check-locks` checks
all reviewed npm graphs with `npm ci --dry-run --ignore-scripts`. This catches
inconsistent locks early. It can consult registry metadata, but does not run
package lifecycle scripts or install agents. Nova 1.1.59 uses an explicit UUID
override matching its bundled dependency; see the ACP provider documentation.

The image does not enable providers in Paseo or include any provider credentials. Complete each provider's own interactive authentication as the `paseo` user. The Oh My Pi toggle remains a Paseo setting and is not changed by installing its CLI. Antigravity can run with broad workspace/command permissions in Paseo; enable it only if that access is intended.

At startup, a Python helper walks verified file descriptors below `/home/paseo`
and repairs ownership to `1000:1000`. It rejects symlink ancestors, skips symbolic
links, hardlinked regular files and nested mounts (including same-filesystem bind
mounts), and confines config overrides to this home. It makes the home private
(`700`), retains private Codex/Claude/GitHub config modes, then delegates to the
original Tini entrypoint. It fails startup if the home or mount identity cannot
be verified. Existing volumes and file contents are preserved.

## GitHub Actions workflow

The repository includes a manually triggered multi-architecture build workflow.
Configure the following under **Settings → Secrets and variables → Actions**:

- Variable `DOCKERHUB_USERNAME`: the Docker Hub account used to publish.
- Variable `DOCKERHUB_IMAGE`: the full image reference, including a version tag,
  for example `docker.io/your-namespace/paseo-agent-clis:your-version`.
- Secret `DOCKERHUB_TOKEN`: a Docker Hub access token with permission to push to
  the selected image repository.

Create the Docker Hub repository before publishing and choose its visibility
according to your distribution requirements. Private images require pull
credentials on the deployment host. Run **Build and publish Paseo CLI image**
from the Actions tab after configuring these values. Never commit credentials.

The workflow validates the startup wrapper and provider smoke checks, runs the ownership test, then builds and pushes `linux/amd64` and `linux/arm64`.

## Build and publish locally

If using another CI runner or local Buildx instead, authenticate to Docker Hub through its credential prompt/secret store and run:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag docker.io/your-namespace/paseo-agent-clis:your-version \
  --push .
```

The Docker Hub repository must exist and allow pushes. Keep it private unless public distribution is intentional. Do not put credentials in this file or in command arguments; authenticate interactively or through the runner's secret store.

## Deploy with Docker Compose

Set `PASEO_PASSWORD` through the deployment platform's secret/environment configuration before
deploying. The hardened entrypoint refuses to start the daemon without it; the
base image's unauthenticated-control warning is no longer sufficient. Do not
commit or log the password. Restrict published ports and remote
access according to your deployment policy.

Set the Paseo service's Compose `image:` reference to the published image, for
example `docker.io/your-namespace/paseo-agent-clis:your-version`. Validate the
configuration with `docker compose config --quiet`, then pull and recreate the
service with `docker compose pull SERVICE` and `docker compose up -d SERVICE`,
replacing `SERVICE` with its Compose service name. Preserve the persistent
`/home/paseo` and `/workspace` volumes when updating an existing deployment.

Dokploy can also manage this Compose deployment: configure the image reference
and environment variables in the platform, then redeploy while retaining the
existing volumes.

## Authenticate inside the running container

The init wrapper repairs GitHub CLI configuration permissions before launching Paseo:
directories use `700`, regular files (including `config.yml` and `hosts.yml`) use
`600`, and ownership is `1000:1000` when init runs as root. It honors
`GH_CONFIG_DIR`, falling back to `${XDG_CONFIG_HOME:-/home/paseo/.config}/gh`.
Keep this directory in the persistent home. Custom paths outside the home and
nested mounts require an administrator to set their permissions separately; init
never repairs them automatically. Hardlinked configuration files must be replaced
with independent copies before authentication. The wrapper restores owner access
on config parents, skips symlinks, and does not create authentication files.
Start the container with the image's default entrypoint and initial user
so it can repair root-owned state and drop privileges with `gosu` before invoking
the original Paseo entrypoint's directory preparation. The daemon runs as paseo.

This repair runs at startup, not continuously. After deploying the rebuilt image,
preserve the existing volumes and restart/recreate the service to apply it. Always
authenticate as `paseo`; a later root login can recreate inaccessible files.

From the Docker host (replace `paseo` with the actual container name):

```bash
docker exec -it --user paseo paseo gh auth login --hostname github.com --git-protocol https --web
docker exec -it --user paseo paseo gh auth status
docker exec -it --user paseo paseo gh auth setup-git
```

If using the container console as root, first run `su - paseo`. A clipboard warning
in a headless container does not prevent login: manually enter the displayed code
at the displayed URL using your computer's browser.

Run each provider CLI from the Docker host/container console as the `paseo` user and complete its own interactive sign-in. The installed command names are `codex`, `claude`, `copilot`, `opencode`, `pi`, `omp`, `agy`, `muse`, and `gh`. Do not copy host authentication directories into the container or put credentials in the image, Compose, or logs.

To connect a GitHub repository, authenticate `gh` inside the container and clone into a new directory on the persistent workspace volume:

```bash
gh auth login
gh auth setup-git
gh repo clone OWNER/REPO /workspace/REPO
```

Complete the login flow in the terminal/browser without sharing its device code or token. Then select `/workspace/REPO` in Paseo. Private repositories require an account with access. The login state stays in the persistent `/home/paseo` volume; treat that volume as sensitive because `gh` may store its token there when no OS credential store is available.

For example, verify Codex and Claude discovery with:

```bash
docker exec -it --user paseo paseo paseo provider diagnostic codex --json
docker exec -it --user paseo paseo paseo provider diagnostic claude
```

The persistent `/home/paseo` volume keeps each CLI's configuration and authentication across redeploys. A successful image build proves the commands are installed; provider login and a fresh Paseo session are still required to verify account access.

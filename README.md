# paseo-agent-image

Version-pinned Docker image for Paseo with native agent CLIs, GitHub CLI and Linux ACP agents.

See [BUILDING.md](BUILDING.md) for builds and deployment, and
[docs/acp-providers.md](docs/acp-providers.md) for ACP installation, activation,
authentication and architecture limits.

See [docs/security-fixes.md](docs/security-fixes.md) for the security corrections,
validation evidence and remaining deployment checks. Set `PASEO_PASSWORD` before
starting the daemon.

To publish your own image, configure the `DOCKERHUB_USERNAME` and
`DOCKERHUB_IMAGE` Actions variables and the `DOCKERHUB_TOKEN` secret as described
in [BUILDING.md](BUILDING.md#github-actions-workflow).

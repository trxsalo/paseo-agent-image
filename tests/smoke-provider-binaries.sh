#!/bin/sh
set -eu

for cli in codex claude copilot opencode pi omp agy muse gh; do
  command -v "$cli" >/dev/null 2>&1 || {
    printf 'missing provider CLI: %s\n' "$cli" >&2
    exit 1
  }
done

# These version checks must not perform provider authentication.
for cli in codex claude copilot opencode pi omp gh; do
  if ! timeout 45s "$cli" --version >/dev/null 2>&1; then
    printf 'provider CLI version check failed: %s\n' "$cli" >&2
    exit 1
  fi
done

test -x "$(command -v agy)"
test -x "$(command -v muse)"
sh -n "$(command -v muse)"
bash -n /usr/local/share/paseo-muse-launcher.sh
printf 'provider_cli_smoke=passed\n'

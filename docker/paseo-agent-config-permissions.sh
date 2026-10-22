#!/bin/sh
set -eu

home=/home/paseo
codex_home=${CODEX_HOME:-$home/.codex}
claude_config_dir=${CLAUDE_CONFIG_DIR:-$home/.claude}

warn() {
  printf 'paseo-agent-config-permissions: warning: %s\n' "$*" >&2
}

# All supported provider CLIs store auth/state below the persistent home. Repair
# only mismatched owners, without following symlinks or crossing mount points.
if [ "$(id -u)" -eq 0 ] && [ -d "$home" ] && [ ! -L "$home" ]; then
  chown 1000:1000 -- "$home" || warn "could not set owner 1000:1000 on $home"
  if ! find "$home" -xdev -mindepth 1 ! -type l \
    \( ! -uid 1000 -o ! -gid 1000 \) \
    -exec chown 1000:1000 {} +; then
    warn "could not repair every mismatched owner under $home"
  fi
fi

# Keep Codex's private files locked down; Claude's configuration is private too.
for dir in "$codex_home" "$codex_home/tmp" "$claude_config_dir"; do
  if [ -d "$dir" ] && [ ! -L "$dir" ]; then
    chmod 700 -- "$dir" || warn "could not set mode 700 on $dir"
  fi
done

for file in "$codex_home/config.toml" "$home/.claude.json"; do
  if [ -f "$file" ] && [ ! -L "$file" ]; then
    chmod 600 -- "$file" || warn "could not set mode 600 on $file"
  fi
done

# Preserve the pinned base image's init/signal handling and privilege drop.
exec /usr/bin/tini -- /usr/local/bin/paseo-docker-entrypoint "$@"

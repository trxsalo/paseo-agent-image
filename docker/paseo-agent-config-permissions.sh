#!/bin/sh
set -eu

home=${HOME:-/home/paseo}
codex_home=${CODEX_HOME:-$home/.codex}
claude_config_dir=${CLAUDE_CONFIG_DIR:-$home/.claude}
xdg_config_home=${XDG_CONFIG_HOME:-$home/.config}

warn() {
  printf 'paseo-agent-config-permissions: warning: %s\n' "$*" >&2
}

# /home/paseo is a persistent volume, so build-time ownership changes do not
# reach it. Repair provider-owned paths before Paseo drops privileges.
if [ "$(id -u)" -eq 0 ]; then
  for path in \
    "$codex_home" \
    "$claude_config_dir" \
    "$home/.claude.json" \
    "$xdg_config_home" \
    "$home"/.gemini \
    "$home"/.aider* \
    "$home"/.opencode
  do
    if [ -L "$path" ]; then
      warn "skipping symlink: $path"
    elif [ -e "$path" ]; then
      if ! chown -R 1000:1000 -- "$path"; then
        warn "could not set owner 1000:1000 on $path"
      fi
    fi
  done

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
fi

# Preserve the pinned base image's init/signal handling and privilege drop.
exec /usr/bin/tini -- /usr/local/bin/paseo-docker-entrypoint "$@"

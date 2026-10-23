#!/bin/sh
set -eu

# The pinned base otherwise only warns and accepts unauthenticated control.
if [ "$#" -eq 0 ] && [ -z "${PASEO_PASSWORD:-}" ]; then
  printf '%s\n' 'paseo-init: PASEO_PASSWORD is required to start the daemon.' >&2
  exit 1
fi

home=/home/paseo
# Repair verified descriptors; do not fall back to pathname-based chown/chmod.
/usr/bin/python3 -I -S /usr/local/libexec/paseo-repair-permissions.py "$home"

# Run upstream ensure_dir logic without root privileges too. Its pathname-based
# mkdir/stat/chown must never undo the descriptor-based repair's link protections.
if [ "$(/usr/bin/id -u)" -eq 0 ]; then
  exec /usr/bin/tini -- /usr/sbin/gosu paseo /usr/local/bin/paseo-docker-entrypoint "$@"
fi
exec /usr/bin/tini -- /usr/local/bin/paseo-docker-entrypoint "$@"

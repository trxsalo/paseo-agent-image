#!/bin/sh
set -eu

home=${HOME:-/home/paseo}
source=/usr/local/share/paseo-muse-launcher.sh
expected_sha256=c6db294799a190ca380da274beb3b9c0e160e0da9681a3d364ce8b0e5fa3a4bc
install_dir=$home/.local/bin
launcher=$install_dir/muse-launcher

if [ ! -r "$source" ]; then
  printf 'muse: pinned launcher is missing: %s\n' "$source" >&2
  exit 1
fi
mkdir -p -- "$install_dir"
current_sha256=
if [ -f "$launcher" ] && [ ! -L "$launcher" ]; then
  current_sha256=$(sha256sum -- "$launcher")
  current_sha256=${current_sha256%% *}
fi
if [ "$current_sha256" != "$expected_sha256" ]; then
  tmp=$launcher.tmp.$$
  cp -- "$source" "$tmp"
  chmod 0755 -- "$tmp"
  mv -f -- "$tmp" "$launcher"
fi

exec "$launcher" "$@"

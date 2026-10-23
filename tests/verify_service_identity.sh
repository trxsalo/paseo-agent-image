#!/bin/sh
set -eu
test "$(/usr/bin/id -u)" = 1000
test "$(/usr/bin/stat -c %u /etc)" = 0
test -L "$CODEX_HOME"
printf 'service_uid=1000\nexternal_directory_owner=0\n'

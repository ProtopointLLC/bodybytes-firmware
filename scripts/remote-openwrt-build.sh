#!/usr/bin/env bash
# Runs the OpenWrt build on a remote "fat" build machine over SSH, then
# syncs build_dir/staging_dir/bin/dl back so this machine can continue
# incremental builds (`make V=s world -j$(nproc)`) once the remote is
# offline. Requires: same absolute repo path on both machines, Nix with
# flakes installed remotely, and passwordless SSH to the host below.
#
# Usage (quote $(nproc) so it evaluates on the remote, not your shell):
#   REMOTE_HOST=<ssh alias> scripts/remote-openwrt-build.sh V=s world -j'$(nproc)'
#   REMOTE_HOST=<ssh alias> scripts/remote-openwrt-build.sh download
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: REMOTE_HOST=<ssh alias> $0 <make args...>" >&2
  exit 1
fi

: "${REMOTE_HOST:?REMOTE_HOST env var must be set to the SSH alias of the build host}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_PATH="$REPO_ROOT"

RSYNC_OPTS=(-a --info=progress2 --exclude='.git' --exclude='.direnv')

rsync "${RSYNC_OPTS[@]}" "$REPO_ROOT/" "$REMOTE_HOST:$REMOTE_PATH/"

ssh "$REMOTE_HOST" bash -s <<EOF
set -e
cd "$REMOTE_PATH"
nix run .#openwrt -- -c 'cd openwrt && make $*'
EOF

rsync "${RSYNC_OPTS[@]}" --delete "$REMOTE_HOST:$REMOTE_PATH/" "$REPO_ROOT/"

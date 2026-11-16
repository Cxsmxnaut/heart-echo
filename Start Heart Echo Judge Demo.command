#!/bin/zsh
set -eu
cd "${0:A:h}/care-assistant" || exit 1
if ! command -v node >/dev/null 2>&1; then
  print -u2 'Install Node.js 22 or newer, then run npm ci in care-assistant.'
  exit 1
fi
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'; then
  print -u2 'Heart Echo judge mode needs Node.js 22 or newer.'
  exit 1
fi
exec node scripts/start-judge.js "$@"

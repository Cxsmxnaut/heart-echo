#!/bin/zsh
cd "${0:A:h}/care-assistant" || exit 1
node --env-file-if-exists=.env scripts/start-demo.js

#!/bin/zsh
cd "${0:A:h}/care-assistant" || exit 1
node scripts/setup-gemini.js

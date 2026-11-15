#!/bin/sh
set -eu
CARE_CLI_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CARE_APP_ROOT=$(CDPATH= cd -- "$CARE_CLI_DIR/../.." && pwd)
export KAGGLE_CONFIG_DIR="$CARE_APP_ROOT/finetuning/runs/kaggle-cli-config"
exec "$CARE_APP_ROOT/finetuning/runs/kaggle-cli-venv/bin/kaggle" "$@"

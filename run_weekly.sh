#!/bin/bash
# Wrapper invoked by launchd. Sources .env, then runs the translator.
set -e
cd "$(dirname "$0")"
set -a
# shellcheck disable=SC1091
source .env
set +a
exec ./.venv/bin/python -u photonbox_weekly.py

#!/bin/bash
# shellcheck source=tasks/pretty_log.sh
set -euo pipefail

env=${1:-"dev"}

# clear command-line parameters
set --
source tasks/pretty_log.sh

pretty_log "Setting up backend for $env"

if [ "$env" = "dev" ]; then
    pretty_log "Testing UI interface will become available at /gradio route of app"
    bash modal serve app.py
else
    pretty_log "Deploying app to $env"
    bash modal deploy app.py
fi

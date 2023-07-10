#!/bin/bash
# shellcheck source=tasks/pretty_log.sh
set -euo pipefail

env=${1:-"dev"}

# clear command-line parameters
set --
source tasks/pretty_log.sh

pretty_log "Setting up frontend for $env"

if [ "$env" = "dev" ]; then
    modal serve bot
else
    pretty_log "Deploying app to $env"
    modal deploy bot
fi

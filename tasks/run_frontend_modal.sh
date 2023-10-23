#!/bin/bash
# shellcheck source=tasks/pretty_log.sh
set -euo pipefail

style=${1:-"serve"}

# clear command-line parameters
set --
source tasks/pretty_log.sh

if [ "$style" = "deploy" ]; then
    pretty_log "Deploying app"
    modal deploy app.bot
else
    pretty_log "Serving app -- changes to local files will trigger update"
    modal serve app.bot
fi

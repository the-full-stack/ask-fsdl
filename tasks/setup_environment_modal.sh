#!/bin/bash
# shellcheck source=tasks/pretty_log.sh
set -euo pipefail

export env=${1:-"dev"}

# clear command-line parameters
set --
source tasks/pretty_log.sh

if modal environment list --json | grep -q "\"name\".*\"$env\""; then
  pretty_log "Found modal environment $env"
else
  pretty_log "Setting up modal environment $env"
  modal environment create "$env"
fi

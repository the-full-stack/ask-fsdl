#!/bin/bash
set -euo pipefail

pretty_log() {
    local ORANGE_BOLD='\033[1;38;5;214m'
    local RESET='\033[0m'
    echo -e "${ORANGE_BOLD}###\n# 🥞:${RESET} $1\n${ORANGE_BOLD}###${RESET}"
}

TO_PRINT=${1:-}
if [[ -n "$TO_PRINT" ]]; then
    pretty_log "$TO_PRINT"
fi

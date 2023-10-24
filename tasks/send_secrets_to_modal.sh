#!/bin/bash
# shellcheck source=tasks/pretty_log.sh
set -euo pipefail

LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY:-""}

# clear command-line parameters
set --
source tasks/pretty_log.sh

modal secret create mongodb-fsdl MONGODB_USER="$MONGODB_USER" MONGODB_HOST="$MONGODB_HOST" MONGODB_PASSWORD="$MONGODB_PASSWORD"
modal secret create openai-api-key-fsdl OPENAI_API_KEY="$OPENAI_API_KEY"

if [ "$LANGCHAIN_API_KEY" = "" ]; then
  pretty_log "LANGHAIN_API_KEY not set. Logging to LangSmith will not be available."
  LANGCHAIN_TRACING_V2=false
  LANGCHAIN_ENDPOINT=""
fi

modal secret create langchain-api-key-fsdl LANGCHAIN_API_KEY="$LANGCHAIN_API_KEY" LANGCHAIN_TRACING_V2="$LANGCHAIN_TRACING_V2" LANGCHAIN_ENDPOINT="$LANGCHAIN_ENDPOINT" LANGCHAIN_PROJECT="$LANGCHAIN_PROJECT"

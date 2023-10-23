#!/bin/bash
set -euo pipefail

# set empty defaults
drop=false
db=""
collection=""

# parse arguments, thanks GPT-4
while (( "$#" )); do
  case "$1" in
    --drop)
      drop=true
      shift
      ;;
    --db)
      if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
        db=$2
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    --collection)
      if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
        collection=$2
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    -*) # error on all other flags
      echo "Error: Unsupported flag $1" >&2
      exit 1
      ;;
  esac
done

db=${db:-$MONGODB_DATABASE}
collection=${collection:-$MONGODB_COLLECTION}

# clear command-line parameters
set --
source tasks/pretty_log.sh

if [ $drop ]; then
  pretty_log "Dropping collection $collection in $db"
  modal run app.main::drop_docs --db "$db" --collection "$collection"
fi

pretty_log "Extracting video transcripts"
modal run etl/videos.py --json-path data/videos.json --db "$db" --collection "$collection"

pretty_log "Extracting Markdown lectures"
modal run etl/markdown.py --json-path data/lectures-2022.json --db "$db" --collection "$collection"

pretty_log "Extracting paper PDFs"
modal run etl/pdfs.py --json-path data/llm-papers.json --db "$db" --collection "$collection"

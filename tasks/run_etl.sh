#!/bin/bash

flush_flag=${1:-""}

# clear command-line parameters
set --
source tasks/pretty_log.sh

if [ "$flush_flag" = "--flush" ]; then
  pretty_log "Flushing document database"
  modal run etl/shared.py::flush_doc_db
fi

modal run etl/videos.py --json-path data/videos.json
modal run etl/markdown.py --json-path data/lectures-2022.json
modal run etl/pdfs.py --json-path data/llm-papers.json

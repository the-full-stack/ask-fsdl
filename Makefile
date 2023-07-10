# provide ENV=dev to use .env.dev instead of .env
ENV_LOADED :=

ifeq ($(ENV), prod)
    ifneq (,$(wildcard ./.env))
        include .env
        export
				ENV_LOADED := Loaded config from .env
    endif
else
    ifneq (,$(wildcard ./.env.dev))
        include .env.dev
        export
				ENV_LOADED := Loaded config from .env.dev
    endif
endif

.PHONY: help
.DEFAULT_GOAL := help

help: logo ## get a list of all the targets, and their short descriptions
	@# source for the incantation: https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | awk 'BEGIN {FS = ":.*?##"}; {printf "\033[1;38;5;214m%-12s\033[0m %s\n", $$1, $$2}'

it-all: logo document-store vector-index backend frontend ## runs automated deployment steps

frontend: slash-command ## deploy the Discord bot on Modal
	@tasks/pretty_log.sh "Assumes you've set up your bot in Discord"
	bash tasks/run_frontend_modal.sh $(ENV)

slash-command: frontend-secrets ## register the bot's slash command with Discord
	modal run bot::create_slash_command
	@tasks/pretty_log.sh "Slash command registered."

backend: secrets ## deploy the Q&A backend on Modal
	@tasks/pretty_log.sh "Assumes you've set up the vector index, see vector-index"
	bash tasks/run_backend_modal.sh $(ENV)

cli-query: secrets ## run a query via a CLI interface
	@tasks/pretty_log.sh "Assumes you've set up the vector index"
	modal run app.py::stub.cli --query "${QUERY}"

vector-index: secrets ## sets up a FAISS vector index to the application
	@tasks/pretty_log.sh "Assumes you've set up the document storage, see document-store"
	modal run app.py::stub.create_vector_index --db $(MONGODB_DATABASE) --collection $(MONGODB_COLLECTION)

document-store: secrets ## creates a MongoDB collection that contains the document corpus
	@tasks/pretty_log.sh "See docstore.py and the ETL notebook for details"
	tasks/run_etl.sh --drop --db $(MONGODB_DATABASE) --collection $(MONGODB_COLLECTION)

debugger: modal-auth ## starts a debugger running in our container but accessible via the terminal
	modal shell app.py

frontend-secrets: modal-auth
	@$(if $(value DISCORD_AUTH),, \
		$(error DISCORD_AUTH is not set. Please set it before running this target.))
	@$(if $(value DISCORD_PUBLIC_KEY),, \
		$(error DISCORD_PUBLIC_KEY is not set. Please set it before running this target.))
	bash tasks/send_frontend_secrets_to_modal.sh

secrets: modal-auth  ## pushes secrets from .env to Modal
	@$(if $(value OPENAI_API_KEY),, \
		$(error OPENAI_API_KEY is not set. Please set it before running this target.))
	@$(if $(value MONGODB_HOST),, \
		$(error MONGODB_HOST is not set. Please set it before running this target.))
	@$(if $(value MONGODB_USER),, \
		$(error MONGODB_USER is not set. Please set it before running this target.))
	@$(if $(value MONGODB_PASSWORD),, \
		$(error MONGODB_PASSWORD is not set. Please set it before running this target.))
	bash tasks/send_secrets_to_modal.sh

modal-auth: environment ## confirms authentication with Modal, using secrets from `.env` file
	@tasks/pretty_log.sh "If you haven't gotten a Modal token yet, run make modal-token"
	@$(if $(value MODAL_TOKEN_ID),, \
		$(error MODAL_TOKEN_ID is not set. Please set it before running this target. See make modal-token.))
	@$(if $(value MODAL_TOKEN_SECRET),, \
		$(error MODAL_TOKEN_SECRET is not set. Please set it before running this target. See make modal-token.))
	@modal token set --token-id $(MODAL_TOKEN_ID) --token-secret $(MODAL_TOKEN_SECRET)

modal-token: environment ## creates token ID and secret for authentication with modal
	modal token new
	@tasks/pretty_log.sh "Copy the token info from the file mentioned above into .env"

environment: ## installs required environment for deployment and corpus generation
	@if [ -z "$(ENV_LOADED)" ]; then \
			echo "Error: Configuration file not found" >&2; \
			exit 1; \
    else \
			tasks/pretty_log.sh "$(ENV_LOADED)"; \
	fi
	python -m pip install -qqq -r requirements.txt

dev-environment: environment  ## installs required environment for development
	python -m pip install -qqq -r requirements-dev.txt

logo:  ## prints the logo
	@cat logo.txt; echo "\n"

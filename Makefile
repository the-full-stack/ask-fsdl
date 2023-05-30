ifneq (,$(wildcard ./.env))
    include .env
    export
endif

.PHONY: help
.DEFAULT_GOAL := help

help: ## get a list of all the targets, and their short descriptions
	@# source for the incantation: https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | awk 'BEGIN {FS = ":.*?##"}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

it-all: environment secrets document-store vector-index backend discord-bot ## runs all automated steps to get the application up and running

frontend: environment pulumi-config ## deploy the Discord bot server on AWS
	@echo "###"
	@echo "# 🥞: Assumes you've set up your bot in Discord, see https://discordpy.readthedocs.io/en/stable/discord.html
	@echo "###"
	pulumi -C bot/ up --yes

discord-bot: environment ## run the Discord bot server locally
	@echo "###"
	@echo "# 🥞: Assumes you've set up your bot in Discord, see https://discordpy.readthedocs.io/en/stable/discord.html
	@echo "###"
	python bot/run.py --dev

backend: modal-auth ## deploy the Q&A backend on Modal
	@echo "###"
	@echo "# 🥞: Assumes you've set up the vector index"
	@echo "###"
	modal deploy app.py
	@echo "###"
	@echo "# 🥞: Gradio interface available at /gradio route"
	@echo "###"

cli-query: modal-auth ## run a query via a CLI interface
	@echo "###"
	@echo "# 🥞: Assumes you've set up the vector storage"
	@echo "###"
	modal run app.py::stub.cli --query "${QUERY}"

vector-index: modal-auth ## sets up a FAISS vector index to the application
	@echo "###"
	@echo "# 🥞: Assumes you've set up the document storage, see make document-store"
	@echo "###"
	modal run app.py::stub.sync_vector_db_to_doc_db

document-store: environment secrets ## creates a MongoDB collection that contains the document corpus
	@echo "###"
	@echo "# 🥞: See docstore.py and the ETL notebook for details"
	@echo "###"
	modal run etl/shared.py::flush_doc_db # start from scratch
	modal run etl/videos.py --json-path data/videos.json
	modal run etl/markdown.py --json-path data/lectures-2022.json
	modal run etl/pdfs.py --json-path data/llm-papers.json

debugger: modal-auth ## starts a debugger running in our container but accessible via the terminal
	modal run app.py::stub.debug

modal-auth: environment ## confirms authentication with Modal, using secrets from `.env` file
	@echo "###"
	@echo "# 🥞: If you haven't gotten a Modal token yet, run make modal-token"
	@echo "###"
	@$(if $(value MODAL_TOKEN_ID),, \
		$(error MODAL_TOKEN_ID is not set. Please set it before running this target.))
	@$(if $(value MODAL_TOKEN_SECRET),, \
		$(error MODAL_TOKEN_SECRET is not set. Please set it before running this target.))
	@modal token set --token-id $(MODAL_TOKEN_ID) --token-secret $(MODAL_TOKEN_SECRET)

secrets: modal-auth  ## pushes secrets from .env to Modal
	@$(if $(value OPENAI_API_KEY),, \
		$(error OPENAI_API_KEY is not set. Please set it before running this target.))
	@$(if $(value MONGODB_URI),, \
		$(error MONGODB_URI is not set. Please set it before running this target.))
	@$(if $(value MONGODB_USER),, \
		$(error MONGODB_USER is not set. Please set it before running this target.))
	@$(if $(value MONGODB_PASSWORD),, \
		$(error MONGODB_PASSWORD is not set. Please set it before running this target.))
	@modal secret create mongodb-fsdl MONGODB_USER=$(MONGODB_USER) MONGODB_URI=$(MONGODB_URI) MONGODB_PASSWORD=$(MONGODB_PASSWORD)
	@modal secret create openai-api-key-fsdl OPENAI_API_KEY=$(OPENAI_API_KEY)

pulumi-config:  ## adds secrets and config from .env to Pulumi
	@$(if $(value MODAL_USER_NAME),, \
		$(error MODAL_USER_NAME is not set. Please set it before running this target.))
	@$(if $(value DISCORD_AUTH),, \
		$(error DISCORD_AUTH is not set. Please set it before running this target.))
	@pulumi -C bot/ config set MODAL_USER_NAME $(MODAL_USER_NAME)
	@pulumi -C bot/ config set --secret DISCORD_AUTH $(DISCORD_AUTH_DEV)
	@$(if $(value DISCORD_MAINTAINER_ID),pulumi -C bot/ config set --secret DISCORD_MAINTAINER_ID $(DISCORD_MAINTAINER_ID),)
	pulumi -C bot/ config

modal-token: environment ## creates token ID and secret for authentication with modal
	modal token new
	@echo "###"
	@echo "# 🥞: Copy the token info from the file mentioned above into .env"
	@echo "###"

environment: ## installs required environment for deployment and corpus generation
	python -m pip install -qqq -r requirements.txt

dev-environment:  ## installs required environment for development
	python -m pip install -qqq -r requirements-dev.txt

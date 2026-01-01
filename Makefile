#
# Makefile for cfn-lint docker image wrapper
#
# Author: Gareth Budge
# Repo  : https://github.com/gbudge/cfn-lint-docker
#
.DEFAULT_GOAL := help

SHELL := /bin/bash
PYTHON := python3
DOCKER := docker

# --------------- Image Variables ---------------
IMAGE_REPO := cfn-lint
IMAGE_TAG	 := latest

TEST_SCRIPT := run_tests.py

# -------------- Install Variables --------------
PREFIX ?= ~/.local
BINDIR ?= $(PREFIX)/bin
INSTALL_NAME ?= cfn-lint
INSTALL_PATH := $(BINDIR)/$(INSTALL_NAME)

# ------------------- Colors --------------------
CYAN := \033[36m
RESET := \033[0m

# ----------------- Help Target -----------------
.PHONY: help
help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'

# ------------- Maintenance Targets -------------
.PHONY: clean
clean: ## Clean build artifacts
	find . -type d -name "node_modules" -exec rm -rf {} +
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -exec rm -rf {} +

.PHONY: all
all: clean dev-setup build-wolfi test ## Recreate development environment, build, and test
	@echo "All tasks completed successfully."

.PHONY: dev-setup
dev-setup: ## Configure development environment
	$(PYTHON) -m venv .venv
	. .venv/bin/activate
	$(PYTHON) -m pip install -r requirements.txt
	pre-commit install

# ---------------- Build Targets ----------------
.PHONY: build
build: ## Build the official cfn-lint image (alpine)
	$(DOCKER) build . -f Dockerfile -t $(IMAGE_REPO):$(IMAGE_TAG)

.PHONY: build-wolfi
build-wolfi: ## Build the official cfn-lint image (wolfi)
	$(DOCKER) build . -f Dockerfile.wolfi -t $(IMAGE_REPO):$(IMAGE_TAG)

# ---------------- Install Targets ----------------
.PHONY: install
install: ## Install cfn-lint wrapper into PATH
	install -m 755 src/cfn-lint.py $(INSTALL_PATH)

.PHONY: uninstall
uninstall: ## Remove installed cfn-lint wrapper
	rm -f $(INSTALL_PATH)
# ----------------- QA Targets ------------------

.PHONY: test
test: ## Run all tests
	$(MAKE) precommit
	$(MAKE) build-wolfi
	CFN_LINT_IMAGE=$(IMAGE_REPO):$(IMAGE_TAG) $(PYTHON) $(TEST_SCRIPT)

.PHONY: precommit
precommit: ## Run pre-commit checks
	pre-commit run --all-files

# Coin Quant R11 - Makefile
# For Unix-like systems (Linux, macOS)

.PHONY: help setup install test clean run-feeder run-ares run-trader run-all validate

help: ## Show this help message
	@echo "Coin Quant R11 - Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Setup virtual environment and install dependencies
	@echo "Setting up Coin Quant R11..."
	python3 -m venv venv
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -e .
	@echo "Setup complete!"

install: ## Install package in editable mode
	. venv/bin/activate && pip install -e .

test: ## Run validation tests
	. venv/bin/activate && python validate.py

clean: ## Clean up temporary files
	rm -rf __pycache__/
	rm -rf *.pyc
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf test_memory/
	rm -rf shared_data/

run-feeder: ## Run Feeder service
	. venv/bin/activate && python launch.py feeder

run-ares: ## Run ARES service
	. venv/bin/activate && python launch.py ares

run-trader: ## Run Trader service
	. venv/bin/activate && python launch.py trader

run-all: ## Run all services in order
	@echo "Starting all services in order..."
	@echo "1. Starting Feeder Service..."
	. venv/bin/activate && python launch.py feeder &
	sleep 5
	@echo "2. Starting ARES Service..."
	. venv/bin/activate && python launch.py ares &
	sleep 5
	@echo "3. Starting Trader Service..."
	. venv/bin/activate && python launch.py trader &
	@echo "All services started!"

validate: ## Run validation tests
	. venv/bin/activate && python validate.py

check: ## Check system requirements
	@echo "Checking system requirements..."
	@python3 --version
	@echo "Python version check passed"
	@echo "System requirements check complete!"

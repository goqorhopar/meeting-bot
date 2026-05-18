# Makefile for Meeting Bot

.PHONY: help install lint test run docker-build docker-run docker-clean dev prod clean

## help: Show this help message
help:
	@echo "Meeting Bot - Available Commands:"
	@echo ""
	@echo "  make install       - Install all dependencies"
	@echo "  make lint          - Run linting checks"
	@echo "  make test          - Run tests"
	@echo "  make run           - Run locally with uvicorn"
	@echo "  make dev           - Run in development mode with reload"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-run    - Run Docker container"
	@echo "  make docker-compose-up   - Start with docker-compose"
	@echo "  make docker-compose-down - Stop docker-compose"
	@echo "  make clean         - Clean build artifacts"

## install: Install all dependencies
install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Installing Node.js dependencies..."
	npm install --production
	@echo "Dependencies installed successfully!"

## lint: Run linting checks
lint:
	@echo "Checking Python syntax..."
	python -m py_compile main.py config.py tools.py
	@echo "Checking JavaScript syntax..."
	node --check join-meeting.js
	@echo "✅ All linting checks passed!"

## test: Run tests
test:
	@echo "Running syntax tests..."
	python -m py_compile main.py config.py tools.py
	node --check join-meeting.js
	@echo "✅ All tests passed!"

## run: Run locally
run:
	uvicorn main:app --host 0.0.0.0 --port 8080

## dev: Run in development mode
dev:
	uvicorn main:app --host 0.0.0.0 --port 8080 --reload

## docker-build: Build Docker image
docker-build:
	docker build -t meeting-bot:latest .

## docker-run: Run Docker container
docker-run:
	docker run -d -p 8080:8080 --env-file .env --name meeting-bot meeting-bot:latest

## docker-stop: Stop Docker container
docker-stop:
	docker stop meeting-bot || true
	docker rm meeting-bot || true

## docker-clean: Clean Docker resources
docker-clean:
	docker rmi meeting-bot:latest || true
	docker system prune -f

## docker-compose-up: Start with docker-compose
docker-compose-up:
	docker-compose up -d

## docker-compose-down: Stop docker-compose
docker-compose-down:
	docker-compose down

## docker-compose-logs: View docker-compose logs
docker-compose-logs:
	docker-compose logs -f

## prod: Production run command
prod:
	uvicorn main:app --host 0.0.0.0 --port 8080 --workers 4

## clean: Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + || true
	find . -type f -name "*.pyc" -delete || true
	find . -type f -name "*.pyo" -delete || true
	rm -rf node_modules || true
	rm -rf dist build *.egg-info || true
	rm -rf recordings/* transcripts/* reports/* || true
	@echo "Clean complete!"

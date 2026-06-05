DC = docker compose

.PHONY: help up down restart build rebuild logs logs-bot logs-api \
        test ps shell-bot shell-api clean setup \
        deploy deploy-api deploy-landing

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  deploy         Full redeploy: pull + build api+bot + up + landing"
	@echo "  deploy-api     Pull + rebuild api only + up + landing"
	@echo "  deploy-landing Update landing HTML only (no rebuild)"
	@echo ""
	@echo "  setup          Copy .env.example → .env (first run)"
	@echo "  build          Build images"
	@echo "  rebuild        Force rebuild without cache"
	@echo "  up             Start bot + api in background"
	@echo "  down           Stop and remove containers"
	@echo "  restart        Restart all services"
	@echo "  logs           Follow logs for all services"
	@echo "  logs-bot       Follow bot logs"
	@echo "  logs-api       Follow api logs"
	@echo "  ps             Show running containers"
	@echo "  test           Run pytest in isolated container"
	@echo "  shell-bot      Open shell in bot container"
	@echo "  shell-api      Open shell in api container"
	@echo "  clean          Remove containers, volumes, and built images"

deploy:
	@bash deploy.sh

deploy-api:
	@bash deploy.sh --api

deploy-landing:
	@bash deploy.sh --landing

setup:
	@test -f .env || (cp .env.example .env && echo ".env created from .env.example — fill in your values")

build:
	$(DC) build

rebuild:
	$(DC) build --no-cache

up:
	$(DC) up -d bot api

down:
	$(DC) down

restart:
	$(DC) restart

logs:
	$(DC) logs -f

logs-bot:
	$(DC) logs -f bot

logs-api:
	$(DC) logs -f api

ps:
	$(DC) ps

test:
	$(DC) --profile test run --rm test

shell-bot:
	$(DC) exec bot /bin/bash

shell-api:
	$(DC) exec api /bin/bash

clean:
	$(DC) down -v --rmi local

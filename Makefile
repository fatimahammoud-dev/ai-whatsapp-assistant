# Common tasks, all run inside the dev container so nobody needs a local
# Python. `make` on its own lists everything.
#
# The dev image already ships ruff, black and pytest: docker-compose.override.yml
# builds it with REQUIREMENTS_FILE=requirements-dev.txt.

DC        := docker compose
PROD      := docker compose -f docker-compose.yml
EXEC      := $(DC) exec -T app
EXEC_TTY  := $(DC) exec app

.DEFAULT_GOAL := help
.PHONY: help up down restart rebuild logs ps shell bash migrate migrations \
        superuser seed test cov lint format check deploy-check ci \
        prod-up prod-up-http prod-down prod-logs smoke expect secret-key encryption-key clean

help:  ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- development stack -----------------------------------------------------

up:  ## Start the dev stack (runserver on :8000)
	# Always --build: both compose files produce the same image name, so a
	# previous `make prod-up` leaves behind an image with no dev dependencies.
	# The build is cached, so this costs a second when nothing changed.
	$(DC) up -d --build

down:  ## Stop the dev stack
	$(DC) down

restart:  ## Recreate the app container, picking up .env changes
	# `docker compose restart` keeps the old environment; only a recreate
	# re-reads env_file.
	$(DC) up -d --force-recreate app

rebuild:  ## Rebuild the image from scratch and start
	$(DC) build --no-cache
	$(DC) up -d --force-recreate

logs:  ## Follow the app log
	$(DC) logs -f app

ps:  ## Show container status
	$(DC) ps

# --- django ----------------------------------------------------------------

shell:  ## Open a Django shell
	$(EXEC_TTY) python manage.py shell

bash:  ## Open a shell in the app container
	$(EXEC_TTY) bash

migrate:  ## Apply migrations
	$(EXEC) python manage.py migrate

migrations:  ## Generate migrations for model changes
	$(EXEC) python manage.py makemigrations

superuser:  ## Create a superuser
	$(EXEC_TTY) python manage.py createsuperuser

seed:  ## Load the demo tenant, staff users and services
	$(EXEC) python manage.py seed_demo_data

# --- quality ---------------------------------------------------------------

test:  ## Run the test suite
	$(EXEC) python -m pytest -q

cov:  ## Run tests with a coverage report
	$(EXEC) python -m pytest --cov=. --cov-report=term-missing --cov-fail-under=60

lint:  ## Check formatting and lint rules
	$(EXEC) ruff check .
	$(EXEC) black --check .

format:  ## Apply ruff fixes and black formatting
	$(EXEC) ruff check --fix .
	$(EXEC) black .

check:  ## Django system check plus a scan for missing migrations
	$(EXEC) python manage.py check
	$(EXEC) python manage.py makemigrations --check --dry-run

deploy-check:  ## Run the production deployment check
	$(DC) exec -T -e DJANGO_SETTINGS_MODULE=config.settings.prod app \
		python manage.py check --deploy --fail-level WARNING

ci: lint check deploy-check cov  ## Everything CI runs, in the same order

# --- production image ------------------------------------------------------

prod-up:  ## Build and start the production stack (gunicorn)
	$(PROD) up -d --build

prod-up-http:  ## Same, but without the HTTPS redirect, for a local smoke test
	SECURE_SSL_REDIRECT=False $(PROD) up -d --build

prod-down:  ## Stop the production stack
	$(PROD) down

prod-logs:  ## Follow the production app log
	$(PROD) logs -f app

smoke:  ## Assert the running production stack actually works
	@$(PROD) exec -T app python manage.py migrate --check \
		&& echo "  migrations applied"
	@$(MAKE) --no-print-directory expect URL=/health/ CODE=200
	@$(MAKE) --no-print-directory expect URL=/static/admin/css/base.css CODE=200
	@$(MAKE) --no-print-directory expect URL=/ CODE=302
	@if $(PROD) logs app | grep -qE '\[ERROR\]|Traceback'; then \
		echo "  FAIL: errors in the app log"; exit 1; \
	else echo "  app log clean"; fi

expect:
	@code=$$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000$(URL)); \
	if [ "$$code" = "$(CODE)" ]; then \
		printf "  %-32s %s\n" "$(URL)" "$$code"; \
	elif [ "$$code" = "301" ]; then \
		echo "  $(URL) -> 301: the HTTPS redirect is on."; \
		echo "    Run 'make prod-up-http' to smoke-test over plain HTTP."; \
		exit 1; \
	else \
		echo "  FAIL: $(URL) -> $$code (expected $(CODE))"; exit 1; \
	fi

# --- secrets ---------------------------------------------------------------

secret-key:  ## Generate a value for SECRET_KEY
	@$(EXEC) python -c "from django.core.management.utils import \
		get_random_secret_key; print(get_random_secret_key())"

encryption-key:  ## Generate a value for TOKEN_ENCRYPTION_KEY
	@$(EXEC) python -c "from cryptography.fernet import Fernet; \
		print(Fernet.generate_key().decode())"

# --- housekeeping ----------------------------------------------------------

clean:  ## Remove caches and collected static files
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov staticfiles
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

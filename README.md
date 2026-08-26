# AI WhatsApp Assistant

Backend service for an AI-powered WhatsApp booking assistant built with Python and Django.

## Local Development Setup

### Requirements

- Python 3.12+
- Git

### 1. Clone the repository

```bash
git clone https://github.com/fatimahammoud-dev/ai-whatsapp-assistant.git
cd ai-whatsapp-assistant

Backend service for an AI-powered WhatsApp booking assistant built with Python and Django.

## Project Overview

The project is being developed as a backend service for handling WhatsApp conversations and appointment-booking workflows.

The current implementation focuses on establishing a clean and reliable backend foundation before adding the WhatsApp and AI integrations.

## Current Development

The project currently includes:

- Django backend structure
- Development and production settings
- PostgreSQL database support
- Redis service
- Docker and Docker Compose setup
- Environment-based configuration
- GitHub Actions CI
- Ruff code quality checks
- Black formatting checks
- Automated tests with pytest
- Test coverage checks
- Docker build validation
- Codiff pull request workflow

## Requirements

For Docker-based development:

- Git
- Docker
- Docker Compose

For running the project without Docker:

- Python 3.12+
- PostgreSQL
- Redis

## Local Development Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd ai-whatsapp-assistant
```

### 2. Create the environment file

Copy the example environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Then configure the required values inside `.env`.

Example:

```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

POSTGRES_DB=ai_whatsapp_assistant
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password

DATABASE_URL=postgresql://postgres:your-password@db:5432/ai_whatsapp_assistant
REDIS_URL=redis://redis:6379/0
DJANGO_SETTINGS_MODULE=config.settings.prod
```

Do not commit the `.env` file.

## Run with Docker

Build and start the services:

```bash
docker compose up --build
```

The application will be available at:

```text
http://localhost:8000
```

The Docker environment includes:

- Django application
- PostgreSQL
- Redis

## Database Migrations

Run migrations inside the application container:

```bash
docker compose exec app python manage.py migrate
```

## Django Admin

Create a superuser if needed:

```bash
docker compose exec app python manage.py createsuperuser
```

The Django admin panel is available at:

```text
http://localhost:8000/admin/
```

## Run Tests

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=. --cov-report=term-missing --cov-fail-under=60
```

## Code Quality

Run Ruff:

```bash
ruff check .
```

Run Black formatting check:

```bash
black --check .
```

Run the Django system check:

```bash
python manage.py check
```

## Continuous Integration

GitHub Actions automatically runs on pull requests.

The CI pipeline contains three independent jobs:

- `quality` — Ruff and Black
- `test` — Django system checks and pytest with coverage
- `docker` — Docker image build validation

The jobs run independently so failures can be identified and rerun separately.

## Codiff

The project also uses the Codiff GitHub Action for pull requests.

Codiff generates a visual representation of code changes and relationships to make pull request reviews easier.

## Environment Variables

Sensitive configuration is stored in `.env` and is excluded from Git.

`.env.example` documents the required environment variables without containing real secrets.

## Project Status

The project is currently under active development.

The current phase focuses on infrastructure, backend architecture, authentication, models, automated testing, and preparation for the upcoming WhatsApp integration and asynchronous message processing.
FROM python:3.12-slim AS builder

WORKDIR /app

ARG REQUIREMENTS_FILE=requirements.txt

COPY requirements.txt requirements-dev.txt ./

RUN pip install --no-cache-dir --prefix=/install -r "${REQUIREMENTS_FILE}"


FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /install /usr/local
COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings.prod

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
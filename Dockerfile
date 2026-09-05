FROM python:3.12-slim AS builder

WORKDIR /app

ARG REQUIREMENTS_FILE=requirements.txt

COPY requirements.txt requirements-dev.txt ./

RUN pip install --no-cache-dir --prefix=/install -r "${REQUIREMENTS_FILE}"


FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --home /home/appuser --shell /usr/sbin/nologin appuser

COPY --from=builder /install /usr/local
COPY . .

ENV HOME=/home/appuser
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings.prod

# SECRET_KEY is only needed to import settings here; it is not baked into the image.
RUN SECRET_KEY=build-only-not-a-real-secret python manage.py collectstatic --noinput

RUN chmod +x /app/entrypoint.sh \
    && chown -R appuser:appgroup /app /home/appuser

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
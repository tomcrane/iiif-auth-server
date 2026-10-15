# IIIF Auth demo server, for running in a container (e.g., on ECS / Fargate).
# You don't need Docker to run it locally - see README.md.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # The token database is disposable; keep it out of the application directory
    IIIFAUTH_DATABASE_FILE=/app/data/iiifauth.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY iiifauth ./iiifauth
RUN useradd --system --uid 10001 iiifauth && mkdir data && chown iiifauth data
USER iiifauth

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", \
     "--access-logfile", "-", "--no-control-socket", "iiifauth:app"]

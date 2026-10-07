FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p /app/storage/certificates

CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--pool=threads", "--concurrency=5", "-Q", "certificates"]

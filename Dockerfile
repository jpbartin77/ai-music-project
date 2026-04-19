FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Make src/ importable so gunicorn can find cloud_run_app and its siblings
ENV PYTHONPATH=/app/src

# Cloud Run injects PORT; default to 8080
CMD exec gunicorn \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 1 \
    --threads 4 \
    --timeout 300 \
    cloud_run_app:app

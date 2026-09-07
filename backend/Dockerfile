# Imagen de API + worker Celery (deps en build; sin pip en cada ``compose up``).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Código de referencia en la imagen; en compose se monta ``./backend:/app`` para live-reload.
COPY . .

EXPOSE 8000 9101

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

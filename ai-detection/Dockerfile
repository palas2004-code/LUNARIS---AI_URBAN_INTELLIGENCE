FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY ai_worker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_worker /app/ai_worker

CMD ["python", "-m", "ai_worker.detector"]

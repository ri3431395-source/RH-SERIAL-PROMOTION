FROM python:3.11-slim

# ffmpeg is required for all video processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /data should be mounted as a Railway Volume for persistence
RUN mkdir -p /data/work

CMD ["python", "main.py"]

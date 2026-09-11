FROM python:3.11-slim

# Cài đặt FFmpeg và các thư viện hệ thống
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose cổng 8080 dành cho Web Server Flask
EXPOSE 8080

CMD ["python", "main.py"]

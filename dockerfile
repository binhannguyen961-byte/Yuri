# Sử dụng Python 3.11 bản lightweight
FROM python:3.11-slim

# Cài đặt FFmpeg và các công cụ hệ thống cần thiết cho audio/voice
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Sao chép file requirements vào container
COPY requirements.txt .

# Cài đặt các thư viện Python
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn bot vào container
COPY . .

# Chạy bot Yuri
CMD ["python", "main.py"]

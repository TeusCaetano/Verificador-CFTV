FROM python:3.12-slim
RUN find /etc/apt/sources.list.d -type f -exec sed -i 's|http://deb.debian.org|https://deb.debian.org|g' {} + \
    && apt-get -o Acquire::Retries=3 -o APT::Update::Error-Mode=any update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY frontend frontend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8083", "--no-access-log"]

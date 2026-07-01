FROM python:3.12-slim

# Chromium for PDF generation, fonts for readable output
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install deps first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV CHROME_BIN=/usr/bin/chromium
EXPOSE 8501

# Shell form so $PORT (set by Railway) expands; falls back to 8501 locally
CMD uv run streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0

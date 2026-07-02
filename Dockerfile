FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install deps first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8501

# Shell form so $PORT (set by Railway) expands; falls back to 8501 locally
CMD uv run streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0

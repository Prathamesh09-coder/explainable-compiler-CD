FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better caching
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy source code and static frontend files
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Default port for local runs (cloud providers will override $PORT)
ENV PORT=8000
EXPOSE 8000

# Start Uvicorn bound to 0.0.0.0 and dynamic $PORT
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

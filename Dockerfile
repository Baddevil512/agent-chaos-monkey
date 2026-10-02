# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy package requirement files first for layer caching
COPY requirements.txt setup.py pyproject.toml /app/
COPY chaos_engine /app/chaos_engine
COPY agent_chaos_monkey /app/agent_chaos_monkey

# Install Python packages and dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir fastapi uvicorn requests ujson pydantic

# Copy full application code & static docs
COPY . /app

# Expose HuggingFace Spaces & Cloud Port 7860
EXPOSE 7860

# Environment variables
ENV PORT=7860
ENV PYTHONUNBUFFERED=1

# Command to launch 24/7 cloud scanner server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

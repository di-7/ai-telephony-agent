FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for aec-audio-processing (WebRTC audio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    meson \
    ninja-build \
    pkg-config \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --upgrade -r requirements.txt

# Copy application code
COPY . .

# Expose port (Render will use PORT env var)
EXPOSE 8081

# Run the agent
CMD ["python", "main.py"]

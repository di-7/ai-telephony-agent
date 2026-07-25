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

# Pre-download Kokoro ONNX weights inside the Docker image during BUILD phase
RUN python -c "import urllib.request, os; \
    os.path.exists('kokoro-v1.0.onnx') or urllib.request.urlretrieve('https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx', 'kokoro-v1.0.onnx'); \
    os.path.exists('voices-v1.0.bin') or urllib.request.urlretrieve('https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin', 'voices-v1.0.bin'); \
    print('Kokoro models baked into Docker image successfully!')"

# Expose port (Render will use PORT env var)
EXPOSE 8081

# Run the agent
CMD ["python", "main.py"]

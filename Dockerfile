FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for pipecat and ngrok
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    ffmpeg \
    libportaudio2 \
    wget \
    unzip \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install ngrok
RUN wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz \
    && tar -xvzf ngrok-v3-stable-linux-amd64.tgz \
    && mv ngrok /usr/local/bin/ \
    && rm ngrok-v3-stable-linux-amd64.tgz

# Install uv for package management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml ./
COPY uv.lock* ./

# Install Python dependencies (including all required packages)
RUN uv pip install --system --no-cache \
    "pipecat-ai[sarvam,websocket,cartesia,openai,silero,deepgram,runner,outbound,google]>=0.0.86" \
    "pipecatcloud>=0.2.4" \
    "openpyxl>=3.1.2" \
    "streamlit>=1.52.2" \
    pytz \
    pandas \
    requests \
    python-dotenv \
    loguru \
    fastapi \
    uvicorn \
    httpx \
    bcrypt \
    pyjwt

# Copy all Python application files
COPY bot.py ./
COPY server.py ./
COPY whatsapp_service.py ./
COPY email_service.py ./
COPY excel_service.py ./
COPY greetings.txt ./
COPY app.py ./
COPY webhook.py ./
COPY database.py ./
COPY auth.py ./

# Create customer_data directory
RUN mkdir -p customer_data

# Copy frontend files
COPY frontend ./frontend

# Install frontend dependencies
WORKDIR /app/frontend
RUN npm ci --legacy-peer-deps

# Back to app directory
WORKDIR /app

# Copy .env file if it exists (optional, better to use --env-file at runtime)
COPY .env* ./

# Copy startup script
COPY start.sh ./
RUN chmod +x start.sh

# Expose ports (7860 for backend, 7861 for frontend)
EXPOSE 7860 7861

# Run the startup script
CMD ["./start.sh"]

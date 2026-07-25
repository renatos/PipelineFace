FROM python:3.11-slim

# Instalar pacotes de sistema necessários (FFmpeg, bibliotecas gráficas, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependências Python e navegadores Playwright
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --with-deps

# Copiar os códigos da aplicação
COPY . .

ENV MONGO_URI="mongodb://mongodb:27017"
ENV WHISPER_URL="http://host.docker.internal:9000/asr"
ENV OLLAMA_URL="http://host.docker.internal:11434/api/chat"

EXPOSE 8000

CMD ["python3", "web/server.py"]

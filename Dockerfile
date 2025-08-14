# Dockerfile para Railway
FROM python:3.11-slim

# Instalar Node.js para Baileys API
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Definir diretório de trabalho
WORKDIR /app

# Copiar arquivos do projeto
COPY . .

# Instalar dependências Python
RUN pip install --no-cache-dir \
    python-telegram-bot \
    psycopg2-binary \
    apscheduler \
    pytz \
    qrcode \
    pillow \
    requests \
    python-dotenv \
    flask

# Instalar dependências Node.js
WORKDIR /app/baileys-server
RUN npm install

# Voltar para diretório principal
WORKDIR /app

# Definir variável de ambiente Railway
ENV RAILWAY_ENVIRONMENT=true

# Criar diretório para auth
RUN mkdir -p /app/baileys-server/auth_info

# Expor portas
EXPOSE 5000
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Comando para iniciar
CMD ["python3", "bot_complete.py"]

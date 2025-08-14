# Dockerfile Railway - Node.js + Python com ambiente virtual
FROM node:20-slim

# Atualizar e instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    build-essential \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Criar links simbólicos para usar python3 e pip
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.11 /usr/bin/python

# Verificar versões
RUN echo "✅ Node.js: $(node --version)" && \
    echo "✅ NPM: $(npm --version)" && \
    echo "✅ Python: $(python3 --version)"

# Criar diretório de trabalho
WORKDIR /app

# Copiar requirements.txt e configurar ambiente virtual
COPY requirements.txt .

# Criar venv e instalar pacotes Python nele
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Verificar se os pacotes Python foram instalados corretamente
RUN python -c "import flask, telegram, psycopg2; print('✅ Pacotes Python verificados!')"

# Copiar apenas o package.json do baileys
COPY baileys-server/package.json ./baileys-server/

# Instalar dependências Node.js
WORKDIR /app/baileys-server
RUN npm install --production --no-optional

# Verificar instalação do Baileys
RUN node -e "console.log('✅ Baileys carregado:', typeof require('@whiskeysockets/baileys'))"

# Voltar para diretório principal e copiar todos os arquivos
WORKDIR /app
COPY . .

# Criar diretórios usados pelo sistema
RUN mkdir -p /app/baileys-server/auth_info

# Configurar variáveis de ambiente
ENV PYTHONPATH=/app
ENV NODE_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expor portas usadas
EXPOSE 5000
EXPOSE 3000

# Health check para Railway
HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=5 \
    CMD curl -f http://localhost:5000/health || exit 1

# Comando de inicialização
CMD ["python3", "start_railway.py"]

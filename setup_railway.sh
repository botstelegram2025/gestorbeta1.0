#!/bin/bash

# Script de setup para deploy no Railway
echo "🚀 Preparando projeto para deploy no Railway..."

# Criar estrutura necessária
echo "📁 Organizando arquivos..."

# Limpar node_modules se existir (muito pesado para git)
if [ -d "node_modules" ]; then
    echo "🧹 Limpando node_modules..."
    rm -rf node_modules
fi

# Criar arquivo start.py para Railway
cat > start_railway.py << 'EOF'
#!/usr/bin/env python3
"""
Script de inicialização para Railway
Inicia tanto o bot Python quanto o servidor Baileys
"""

import os
import subprocess
import threading
import time
import signal
import sys

def start_baileys_server():
    """Inicia o servidor Baileys em background"""
    try:
        print("🔄 Iniciando servidor Baileys...")
        os.chdir('/app/baileys-server')
        subprocess.run(['npm', 'start'], check=True)
    except Exception as e:
        print(f"❌ Erro ao iniciar Baileys: {e}")

def start_bot():
    """Inicia o bot principal"""
    try:
        print("🤖 Iniciando bot principal...")
        os.chdir('/app')
        subprocess.run(['python3', 'bot_complete.py'], check=True)
    except Exception as e:
        print(f"❌ Erro ao iniciar bot: {e}")

def signal_handler(sig, frame):
    """Handler para graceful shutdown"""
    print("\n🛑 Parando serviços...")
    sys.exit(0)

if __name__ == "__main__":
    # Configurar signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Iniciar Baileys em thread separada
    baileys_thread = threading.Thread(target=start_baileys_server, daemon=True)
    baileys_thread.start()
    
    # Aguardar um pouco para Baileys iniciar
    time.sleep(5)
    
    # Iniciar bot principal
    start_bot()
EOF

echo "✅ Projeto preparado para Railway!"
echo ""
echo "📋 Próximos passos:"
echo "1. Crie um repositório no GitHub"
echo "2. Faça commit dos arquivos"
echo "3. Conecte com Railway"
echo "4. Configure as variáveis de ambiente"
echo ""
echo "💰 Custo estimado: $2-5/mês (muito mais barato que Replit!)"
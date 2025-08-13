# 🚀 Guia de Deploy - Bot Gestão de Clientes

## 📦 Arquivos Essenciais Incluídos

### 🐍 **Python (Bot Principal)**
- `bot_complete.py` - Bot principal com Flask integrado
- `whatsapp_session_api.py` - API de persistência de sessões WhatsApp
- `database.py` - Gerenciador PostgreSQL
- `templates.py` - Sistema de templates
- `models.py` - Modelos de dados
- `scheduler.py` - Agendamento de mensagens

### 🟢 **Node.js (WhatsApp API)**
- `baileys-server/` - API WhatsApp completa
- `baileys-server/server.js` - Servidor principal
- `baileys-server/package.json` - Dependências Node.js

### ⚙️ **Configuração Deploy**
- `requirements.txt` - Dependências Python
- `runtime.txt` - Versão Python
- `Procfile` - Comando inicialização
- `railway.json` - Config Railway
- `.env.example` - Template variáveis

## 🚀 **Como Fazer Deploy no Railway**

### 1️⃣ **Preparação**
1. Extraia este ZIP
2. Conecte repositório no Railway
3. Configure PostgreSQL no Railway

### 2️⃣ **Variáveis de Ambiente**
Configure no Railway:
```
BOT_TOKEN=seu_token_telegram
ADMIN_CHAT_ID=seu_chat_id
```

### 3️⃣ **Deploy Automático**
O Railway detectará automaticamente:
- Python app principal
- Node.js para Baileys
- PostgreSQL para dados

### 4️⃣ **Portas**
- **Bot/Flask**: 5000 (principal)
- **Baileys API**: 3000 (WhatsApp)

## ✨ **Funcionalidades**

- ✅ **Gestão completa de clientes**
- ✅ **WhatsApp com persistência de sessão**
- ✅ **Templates personalizáveis**
- ✅ **Agendamento automático**
- ✅ **Relatórios detalhados**
- ✅ **Zero downtime** após deploy

## 🔧 **Após Deploy**

1. **Conectar WhatsApp**: Use comando `/conectar_whatsapp`
2. **Escanear QR**: Uma única vez
3. **Sessão salva**: Permanentemente no PostgreSQL
4. **Sistema operacional**: Imediatamente

## 📱 **Comandos Principais**

- `/start` - Iniciar bot
- `/menu` - Menu principal
- `/conectar_whatsapp` - Conectar WhatsApp
- `/status` - Status do sistema
- `/relatorio` - Relatórios

## 🆘 **Suporte**

- **Logs**: Verifique logs do Railway
- **Saúde**: Endpoint `/` mostra status
- **WhatsApp**: Endpoint `/api/session/status`

Sistema 100% testado e pronto para produção!
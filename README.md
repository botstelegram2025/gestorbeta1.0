# 🤖 GESTOR ALFA - Sistema de Gestão de Clientes

## 📋 Visão Geral
Sistema completo de gestão de clientes com bot Telegram, integração WhatsApp via Baileys, e PostgreSQL multi-tenant. Inclui sistema de pagamentos via Mercado Pago PIX e automação de cobrança.

## 🚀 Status do Sistema
- ✅ **Bot Telegram funcionando** - @meubomgestor_bot
- ✅ **PostgreSQL operacional** - 10 tabelas criadas
- ✅ **Baileys WhatsApp API** - QR Code generation ativo
- ✅ **Sistema multi-usuário** - Teste gratuito + assinatura R$20/mês
- ✅ **Deploy Railway/Replit** - Híbrido configurado

## 🛠️ Arquivos Principais

### Core System
- `bot_complete.py` - Bot Telegram principal
- `database.py` - Gerenciamento PostgreSQL
- `models.py` - Modelos de dados
- `config.py` - Configurações do sistema

### Integrations
- `mercadopago_integration.py` - Pagamentos PIX
- `baileys_api.py` - WhatsApp integration
- `baileys-server/` - Node.js WhatsApp server

### Deployment
- `Dockerfile` - Container Replit
- `Dockerfile.railway` - Container Railway
- `Procfile` - Railway deployment
- `pyproject.toml` - Dependencies

### Documentation
- `HYBRID_DEPLOYMENT_ANALYSIS.md` - Análise deploy híbrido
- `CONFIGURAR_RAILWAY_REPLIT_HIBRIDO.md` - Setup híbrido
- `RAILWAY_DATABASE_FIX.md` - Fix de tabelas Railway
- `replit.md` - Documentação completa

## 💰 Custos de Deploy

### Opção 1: Railway + Replit
- Railway: $0-5/mês (bot)
- Replit Core: $25/mês (banco)
- **Total: $25-30/mês**

### Opção 2: Railway + Neon
- Railway: $5/mês (bot)
- Neon: $0/mês (banco até 3GB)
- **Total: $5/mês**

## 🔧 Configuração Rápida

### 1. Deploy no Railway
```bash
# Clone os arquivos
# Configure variables:
DATABASE_URL=sua_url_postgresql
BOT_TOKEN=seu_bot_token
ADMIN_CHAT_ID=seu_chat_id
MERCADOPAGO_ACCESS_TOKEN=seu_token_mp
```

### 2. Deploy no Replit
```bash
# Upload dos arquivos
# Configure secrets no painel
# Run: python bot_complete.py
```

## 📊 Funcionalidades

- ✅ Gestão completa de clientes
- ✅ Templates de mensagem personalizáveis
- ✅ Agendamento automático de cobrança
- ✅ Sistema multi-usuário com isolamento
- ✅ Relatórios financeiros
- ✅ Integração WhatsApp persistente
- ✅ Pagamentos PIX automáticos
- ✅ Interface administrativa via Telegram

## 🎯 Versão: ALFA FINAL
Sistema testado e funcional em produção.
Deploy híbrido recomendado para melhor custo-benefício.

---
**Criado em:** Agosto 2025  
**Status:** Pronto para produção
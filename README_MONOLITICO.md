# Bot de Gestão de Clientes - Versão Monolítica

🚀 **Sistema completo em um único arquivo Python!**

## 📋 Sobre

Esta é a versão consolidada do Bot de Gestão de Clientes, onde todos os módulos foram reunidos em um único arquivo (`bot_monolitico.py`) para facilitar o deploy e a portabilidade.

### ✨ Funcionalidades Completas

- 🤖 **Bot Telegram** - Interface completa de gestão
- 👥 **Multi-usuário** - Sistema de assinaturas com trial gratuito
- 📱 **WhatsApp** - Integração com Baileys API
- 📄 **Templates** - 8 tipos especializados de mensagens
- ⏰ **Automação** - Verificações e envios automáticos
- 💰 **Pagamentos** - Mercado Pago PIX
- 📊 **Relatórios** - Analytics completos
- 🗄️ **PostgreSQL** - Banco multi-tenant

## 🚀 Deploy Rápido

### 1. Baixar Arquivos
```bash
# Apenas 2 arquivos necessários:
# - bot_monolitico.py (código principal)
# - requirements_monolitico.txt (dependências)
```

### 2. Instalar Dependências
```bash
pip install -r requirements_monolitico.txt
```

### 3. Configurar Variáveis de Ambiente
```bash
export BOT_TOKEN="seu_token_telegram"
export ADMIN_CHAT_ID="seu_chat_id_numerico"
export DATABASE_URL="postgresql://user:pass@host:port/db"
export MERCADOPAGO_ACCESS_TOKEN="seu_token_mercadopago"
```

### 4. Executar
```bash
python bot_monolitico.py
```

## 🔧 Configuração Detalhada

### Variáveis Obrigatórias
- `BOT_TOKEN` - Token do bot Telegram (@BotFather)
- `ADMIN_CHAT_ID` - ID numérico do chat do administrador
- `DATABASE_URL` - URL de conexão PostgreSQL

### Variáveis Opcionais
- `MERCADOPAGO_ACCESS_TOKEN` - Para pagamentos PIX (recomendado)
- `PORT` - Porta do servidor Flask (padrão: 5000)

### Servidor Baileys (WhatsApp)
O bot espera um servidor Node.js rodando na porta 3000 para WhatsApp:

```bash
# Em pasta separada, criar servidor Baileys:
npm init -y
npm install @whiskeysockets/baileys express cors

# Criar server.js com API Baileys básica
# Rodar: node server.js
```

## 🏗️ Arquitetura

### Classes Principais
- `BotGestaoClientes` - Bot principal
- `DatabaseManager` - Gestão PostgreSQL
- `MercadoPagoIntegration` - Pagamentos PIX
- `BaileysAPI` - Interface WhatsApp

### Funcionalidades Integradas
- Estados de conversação
- Agendador automático (APScheduler)
- Servidor Flask para webhooks
- Templates com variáveis dinâmicas
- Sistema multi-tenant completo

## 📱 Como Usar

### Para Administradores
1. Envie `/start` para o bot
2. Acesso completo liberado automaticamente
3. Use menu administrativo para gestão

### Para Usuários
1. Envie `/start` para começar
2. Cadastre-se para trial gratuito de 7 dias
3. Configure empresa e PIX
4. Adicione clientes e crie templates
5. Configure WhatsApp
6. Sistema funciona automaticamente

### Menu Principal
```
👥 Gestão de Clientes
📊 Relatórios  
📄 Templates
📱 WhatsApp
⚙️ Configurações
```

## 🔄 Automação

### Verificações Diárias (9h)
- Clientes vencendo hoje
- Clientes vencidos há 1 dia
- Envio automático de mensagens

### Limpeza (2h)
- Logs antigos (>30 dias)
- Sessões expiradas

## 💰 Sistema de Assinaturas

### Trial Gratuito
- 7 dias completos
- Todas as funcionalidades
- Sem cartão de crédito

### Assinatura Mensal
- R$ 20,00/mês
- PIX instantâneo
- Renovação automática
- Acesso ilimitado

## 📊 Métricas e Relatórios

### Períodos Disponíveis
- 7 dias
- 30 dias  
- 3 meses
- 6 meses

### Dados Inclusos
- Receita esperada vs recebida
- Clientes ativos/vencidos/vencendo
- Performance de renovações
- Estatísticas de mensagens

## 🛠️ Desenvolvimento

### Estrutura do Código
```python
# Configurações e constantes
# Modelos de dados (@dataclass)
# DatabaseManager (PostgreSQL)
# MercadoPagoIntegration (PIX)
# BaileysAPI (WhatsApp)
# BotGestaoClientes (principal)
# Agendador (APScheduler)
# Servidor Flask (webhooks)
# Função main()
```

### Logs
- Level: INFO
- Formato: timestamp - name - level - message
- Saída: console (stdout)

### Timezone
- America/Sao_Paulo (fixo)
- Todas as operações respeitam fuso brasileiro

## 🚀 Deploy em Produção

### Railway
```bash
railway login
railway init
railway add postgresql
railway deploy
```

### Heroku
```bash
heroku create sua-app
heroku addons:create heroku-postgresql
heroku config:set BOT_TOKEN=...
git push heroku main
```

### Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements_monolitico.txt .
RUN pip install -r requirements_monolitico.txt

COPY bot_monolitico.py .

CMD ["python", "bot_monolitico.py"]
```

## 📞 Suporte

### Health Check
- Endpoint: `http://localhost:5000/health`
- Retorna: `{"status": "ok", "timestamp": "..."}`

### Logs Importantes
- Inicialização de serviços
- Status de conexões
- Erros de envio
- Verificações automáticas

### Monitoramento
- Bot responde a comandos
- WhatsApp conectado
- Banco acessível  
- Scheduler ativo

## 📈 Performance

### Otimizações Incluídas
- Conexões de banco otimizadas
- Índices de performance
- Threading para Flask
- Autocommit no PostgreSQL
- Cache de configurações

### Limites Recomendados
- Até 1000 clientes por usuário
- Envios: 60 mensagens/minuto (WhatsApp)
- Usuários simultâneos: 100+

---

**🎯 Este arquivo único contém todo o sistema funcional!**

**Total:** ~1000 linhas de código Python puro
**Dependências:** Apenas pacotes pip padrão
**Deploy:** Copy & paste + pip install
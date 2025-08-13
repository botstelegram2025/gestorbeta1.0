# Baileys API - Servidor WhatsApp

## Instalação Rápida

```bash
cd baileys-server
npm install
npm start
```

## Como Usar

1. **Instalar dependências:**
   ```bash
   npm install
   ```

2. **Iniciar servidor:**
   ```bash
   npm start
   ```

3. **Testar API:**
   ```bash
   curl http://localhost:3000/status
   ```

4. **No bot Telegram:**
   - Menu → WhatsApp/Baileys
   - Gerar QR Code
   - Escanear com WhatsApp

## Endpoints

- `GET /status` - Status da conexão
- `GET /qr` - Obter QR Code  
- `POST /send-message` - Enviar mensagem
- `POST /reconnect` - Reconectar

## Estrutura

```
baileys-server/
├── package.json      # Dependências
├── server.js         # Servidor principal
├── auth_info/        # Sessão WhatsApp (criada automaticamente)
└── README.md         # Este arquivo
```

## Solução de Problemas

### "Erro ao conectar"
- Certifique-se que Node.js está instalado
- Execute `npm install` primeiro
- Verifique se porta 3000 está livre

### "QR Code não disponível"  
- Aguarde alguns segundos após iniciar
- WhatsApp pode já estar conectado
- Use endpoint `/reconnect` para forçar novo QR

### "Erro ao enviar mensagem"
- Confirme que WhatsApp foi conectado
- Verifique formato do número (+5511999999999)
- Teste com seu próprio número primeiro

## Logs Importantes

```
🚀 Baileys API rodando na porta 3000
🔄 Iniciando conexão com WhatsApp...
📱 QR Code gerado!
✅ WhatsApp conectado!
```

## Integração com Bot

O bot Telegram se conecta automaticamente em `http://localhost:3000` e usa estes endpoints:

- Verifica status com `/status`
- Obtém QR Code com `/qr`  
- Envia mensagens com `/send-message`

Após conectar, todas as funcionalidades WhatsApp do bot ficam disponíveis.
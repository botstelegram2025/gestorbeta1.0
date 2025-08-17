// server.js — Baileys API (persistência + healthcheck estável)
//
// - Persistência por sessão: useMultiFileAuthState (uma pasta por sessão)
// - /health SEMPRE 200 quando o Node está no ar (ideal para liveness/healthcheck)
// - /ready indica se o servidor inicializou (e quantas sessões estão vivas)
// - /qr, /status/:sessionId, /send-message, /reconnect/:sessionId, /sessions
//
// Requisitos: npm i express cors body-parser pino @whiskeysockets/baileys

const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const pino = require('pino')({ level: process.env.LOG_LEVEL || 'info' });
const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState
} = require('@whiskeysockets/baileys');

// ------------------ Config ------------------
const PORT = process.env.PORT || 3000;
const SESSIONS_DIR = process.env.SESSIONS_DIR || path.join(__dirname, 'sessions');
if (!fs.existsSync(SESSIONS_DIR)) fs.mkdirSync(SESSIONS_DIR, { recursive: true });

// ------------------ Estado ------------------
/** Map<sessionId, { sock, qrCode, isConnected, status, sessionId }> */
const sessions = new Map();
let IS_READY = false;

// ------------------ App ------------------
const app = express();
app.use(cors());
app.use(bodyParser.json({ limit: '2mb' }));

// Health SEMPRE 200 (liveness)
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', uptime: process.uptime() });
});

// Readiness (opcional)
app.get('/ready', (req, res) => {
  const connectedCount = Array.from(sessions.values()).filter(s => s.isConnected).length;
  res.status(200).json({ ready: IS_READY, sessions: sessions.size, connected: connectedCount });
});

// ------------------ Helpers ------------------
function getSessionRecord(sessionId) {
  if (!sessions.has(sessionId)) {
    sessions.set(sessionId, {
      sock: null,
      qrCode: null,
      isConnected: false,
      status: 'disconnected',
      sessionId
    });
  }
  return sessions.get(sessionId);
}

function statusPayload(sessionId) {
  const rec = getSessionRecord(sessionId);
  return {
    connected: Boolean(rec.isConnected),
    status: rec.status, // connected | connecting | disconnected | qr_ready | close | error
    session: rec.sock?.user?.id || null, // JID
    qr_available: Boolean(rec.qrCode),
    timestamp: new Date().toISOString(),
    session_id: sessionId
  };
}

// ------------------ Conexão WhatsApp ------------------
async function connectToWhatsApp(sessionId) {
  const session = getSessionRecord(sessionId);
  const authPath = path.join(SESSIONS_DIR, String(sessionId));
  const { state, saveCreds } = await useMultiFileAuthState(authPath);

  // Evita sockets antigos abertos
  if (session.sock?.end) {
    try { session.sock.end(); } catch (e) {}
  }

  const sock = makeWASocket({
    logger: pino,
    auth: state,
    printQRInTerminal: false,
    browser: ["Baileys-MultiSessao", "Chrome", "1.0"],
    syncFullHistory: false
  });

  session.sock = sock;
  session.status = 'connecting';
  session.isConnected = false;
  session.qrCode = null;

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      session.qrCode = qr;
      session.status = 'qr_ready';
      session.isConnected = false;
    }

    if (connection === 'open') {
      session.status = 'connected';
      session.isConnected = true;
      session.qrCode = null;
    }

    if (connection === 'close') {
      const reason = lastDisconnect?.error?.output?.statusCode || lastDisconnect?.error?.message || 'unknown';
      session.status = 'disconnected';
      session.isConnected = false;
      session.qrCode = null;

      // Reconexão automática leve (opcional)
      if (reason !== DisconnectReason.loggedOut) {
        setTimeout(() => {
          connectToWhatsApp(sessionId).catch(err => pino.error({ err }, 'reconnect failed'));
        }, 2000);
      }
    }
  });

  return session;
}

// ------------------ Rotas API ------------------

// Recupera (ou inicia) QR por sessão (path param)
app.get('/qr/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const session = await connectToWhatsApp(sessionId);
    const payload = statusPayload(sessionId);
    // Se já conectado, não há QR
    if (payload.connected) {
      return res.json({ success: true, data: { ...payload, qr: null, qr_image: null, instructions: 'Já conectado' } });
    }
    // Se QR existe, retorna
    if (session.qrCode) {
      return res.json({ success: true, data: { ...payload, qr: session.qrCode, qr_image: null, instructions: 'Escaneie o QR no WhatsApp' } });
    }
    // Ainda conectando / sem QR (aguardando evento)
    return res.json({ success: true, data: { ...payload, qr: null, qr_image: null, instructions: 'Aguardando QR' } });
  } catch (e) {
    pino.error(e, 'qr error');
    res.status(500).json({ success: false, error: e?.message || 'qr_error' });
  }
});

// Alternativa via query (?sessionId=)
app.get('/qr', async (req, res) => {
  const { sessionId } = req.query;
  if (!sessionId) return res.status(400).json({ success: false, error: 'sessionId é obrigatório' });
  req.params.sessionId = sessionId;
  return app._router.handle(req, res, () => {}, 'get', `/qr/${encodeURIComponent(sessionId)}`);
});

// Status por sessão
app.get('/status/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    // Não obriga reconectar para consultar
    const payload = statusPayload(sessionId);
    return res.json(payload);
  } catch (e) {
    res.status(500).json({ error: e?.message || 'status_error' });
  }
});

// Status global (resumo de todas as sessões em memória)
app.get('/status', (req, res) => {
  const all = Array.from(sessions.keys()).map(sessionId => statusPayload(sessionId));
  res.json({ up: true, sessions: all });
});

// Enviar mensagem
app.post('/send-message', async (req, res) => {
  try {
    const { number, message, session_id } = req.body || {};
    if (!number || !message || !session_id) {
      return res.status(400).json({ success: false, error: 'Campos obrigatórios: number, message, session_id' });
    }
    const session = await connectToWhatsApp(session_id);
    if (!session.sock) throw new Error('Sessão sem socket');
    const jid = number.toString().endsWith('@s.whatsapp.net') ? number : `${number}@s.whatsapp.net`;
    const sent = await session.sock.sendMessage(jid, { text: message });
    return res.json({ success: true, messageId: sent?.key?.id || null, timestamp: Date.now() });
  } catch (e) {
    pino.error(e, 'send-message error');
    res.status(500).json({ success: false, error: e?.message || 'send_message_error' });
  }
});

// Reconnect (restart) da sessão
app.post('/reconnect/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    await connectToWhatsApp(sessionId);
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ success: false, error: e?.message || 'reconnect_error' });
  }
});

// Lista sessões em memória
app.get('/sessions', (req, res) => {
  const list = Array.from(sessions.keys());
  res.json({ success: true, sessions: list });
});

// ------------------ Bootstrap ------------------
async function preloadSessions() {
  try {
    const dirs = fs.readdirSync(SESSIONS_DIR, { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => d.name);
    for (const sid of dirs) {
      try {
        await connectToWhatsApp(sid);
        pino.info({ sid }, 'restored persisted session');
      } catch (e) {
        pino.warn({ sid, err: e?.message || e }, 'failed to restore session');
      }
    }
  } catch (e) {
    pino.warn({ err: e?.message || e }, 'no sessions to preload');
  }
}

const server = app.listen(PORT, () => {
  IS_READY = true; // pronto para receber tráfego HTTP
  pino.info(`Baileys API ouvindo em http://0.0.0.0:${PORT}`);
  // Preload sem bloquear readiness/health
  preloadSessions();
});

process.on('SIGTERM', () => {
  pino.info('SIGTERM recebido, encerrando...');
  server.close(() => process.exit(0));
});

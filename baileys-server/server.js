// Baileys API - persistência LOCAL apenas
// deps: npm i @whiskeysockets/baileys qrcode express cors

const { default: makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const express = require('express');
const QRCode = require('qrcode');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// ===== PERSISTÊNCIA LOCAL =====
const AUTH_BASE_DIR = process.env.AUTH_BASE_DIR || path.join(process.cwd(), 'auth_storage');
// Ex.: em Docker/Railway: AUTH_BASE_DIR=/data

function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

function getAuthPath(sessionId) {
  return path.join(AUTH_BASE_DIR, `auth_info_${sessionId}`);
}

ensureDir(AUTH_BASE_DIR);

// Middlewares
app.use(cors());
app.use(express.json());

// Estado global para múltiplas sessões
// sessionId -> { sock, qrCode, isConnected, status, backupInterval }
const sessions = new Map();

// =============== CONEXÃO WHATSAPP (PERSISTÊNCIA LOCAL) ===============
const connectToWhatsApp = async (sessionId) => {
  try {
    if (!sessionId) throw new Error('sessionId é obrigatório');
    console.log(`🔄 Iniciando conexão com WhatsApp para sessão ${sessionId}...`);

    // Garantir diretório de credenciais local PERSISTENTE
    const authPath = getAuthPath(sessionId);
    ensureDir(authPath);

    // Carregar/gerar arquivos locais (creds.json, keys.json etc.)
    const { state, saveCreds } = await useMultiFileAuthState(authPath);

    // Criar socket da sessão
    const sock = makeWASocket({
      auth: state,
      printQRInTerminal: false, // QR será servido pelo endpoint
      browser: ['Ubuntu', 'Chrome', '22.04.4'],
      connectTimeoutMs: 30_000,
      defaultQueryTimeoutMs: 30_000,
    });

    // Inicializar objeto de sessão (mantendo campos para compatibilidade)
    if (!sessions.has(sessionId)) {
      sessions.set(sessionId, {
        sock: null,
        qrCode: '',
        isConnected: false,
        status: 'initializing',
        backupInterval: null, // não usamos mais, mas mantemos para não quebrar handlers existentes
      });
    }
    const session = sessions.get(sessionId);
    session.sock = sock;

    // Sempre que as credenciais mudarem, salva localmente
    sock.ev.on('creds.update', saveCreds);

    // Eventos de conexão
    sock.ev.on('connection.update', (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        session.qrCode = qr;
        session.status = 'qr_ready';
        console.log(`📱 [${sessionId}] QR Code pronto`);
      }

      if (connection === 'open') {
        session.isConnected = true;
        session.status = 'connected';
        session.qrCode = '';
        console.log(`✅ [${sessionId}] WhatsApp conectado como ${session.sock?.user?.id}`);
      }

      if (connection === 'close') {
        session.isConnected = false;
        session.status = 'disconnected';

        const code =
          lastDisconnect?.error?.output?.statusCode ||
          lastDisconnect?.error?.statusCode ||
          lastDisconnect?.error?.code;

        const loggedOut = code === DisconnectReason.loggedOut;
        console.log(`🔌 [${sessionId}] Conexão fechada. code=${code} loggedOut=${loggedOut}`);

        if (loggedOut) {
          // Sessão inválida/expirada → apagar credenciais para forçar novo pareamento
          try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
          console.log(`🧹 [${sessionId}] Credenciais removidas. Será necessário escanear o QR novamente.`);
          return;
        }

        // Tentar reconectar reaproveitando as credenciais locais
        setTimeout(() => connectToWhatsApp(sessionId), 5_000);
      }

      if (connection === 'connecting' && session.status !== 'connecting') {
        session.status = 'connecting';
        console.log(`🔄 [${sessionId}] Conectando...`);
      }
    });

    return sock;
  } catch (error) {
    console.error(`❌ Erro ao conectar sessão ${sessionId}:`, error);
    const session = sessions.get(sessionId);
    if (session) session.status = 'error';
  }
};

// =============== ENDPOINTS ===============

// Status da API - OBRIGATÓRIO sessionId
app.get('/status/:sessionId', (req, res) => {
  const sessionId = req.params.sessionId;
  if (!sessionId) {
    return res.status(400).json({
      connected: false,
      status: 'error',
      error: 'sessionId é obrigatório',
      qr_available: false,
      timestamp: new Date().toISOString(),
    });
  }

  const session = sessions.get(sessionId);
  if (!session) {
    return res.json({
      connected: false,
      status: 'not_initialized',
      session: null,
      qr_available: false,
      timestamp: new Date().toISOString(),
      session_id: sessionId,
    });
  }

  res.json({
    connected: session.isConnected,
    status: session.status,
    session: session.sock?.user?.id || null,
    qr_available: session.qrCode !== '',
    timestamp: new Date().toISOString(),
    session_id: sessionId,
  });
});

// QR Code - OBRIGATÓRIO sessionId
app.get('/qr/:sessionId', async (req, res) => {
  try {
    const sessionId = req.params.sessionId;
    if (!sessionId) {
      return res.status(400).json({
        success: false,
        error: 'sessionId é obrigatório',
        session_id: null,
      });
    }

    // Inicializar sessão se não existir
    if (!sessions.has(sessionId)) {
      await connectToWhatsApp(sessionId);
      // Aguardar um pouco para QR ser gerado
      await new Promise((r) => setTimeout(r, 2500));
    }

    const session = sessions.get(sessionId);

    if (!session || !session.qrCode) {
      return res.status(404).json({
        success: false,
        error: `QR Code não disponível para sessão ${sessionId}. Tente reconectar.`,
        session_id: sessionId,
      });
    }

    // Gerar imagem QR Code
    const qrImage = await QRCode.toDataURL(session.qrCode);

    res.json({
      success: true,
      qr: session.qrCode,
      qr_image: qrImage,
      instructions: 'Abra WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho',
      session_id: sessionId,
    });
  } catch (error) {
    console.error('❌ Erro ao gerar QR:', error);
    res.status(500).json({
      success: false,
      error: 'Erro ao gerar QR Code',
      session_id: req.params.sessionId,
    });
  }
});

// Enviar mensagem - OBRIGATÓRIO session_id
app.post('/send-message', async (req, res) => {
  try {
    const { number, message, session_id } = req.body;

    if (!session_id) {
      return res.status(400).json({ success: false, error: 'session_id é obrigatório' });
    }
    if (!number || !message) {
      return res.status(400).json({ success: false, error: 'Número e mensagem são obrigatórios' });
    }

    const session = sessions.get(session_id);
    if (!session || !session.isConnected) {
      return res.status(400).json({
        success: false,
        error: `WhatsApp não conectado para sessão ${session_id}`,
        session_id,
      });
    }

    const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
    const result = await session.sock.sendMessage(jid, { text: message });

    console.log(`✅ Mensagem enviada via sessão ${session_id}:`, number, message.substring(0, 50) + '...');

    res.json({
      success: true,
      messageId: result.key.id,
      timestamp: new Date().toISOString(),
      session_id,
    });
  } catch (error) {
    console.error('❌ Erro ao enviar mensagem:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      session_id: req.body.session_id || null,
    });
  }
});

// Reconectar sessão específica (NÃO apaga credenciais locais)
app.post('/reconnect/:sessionId', async (req, res) => {
  try {
    const sessionId = req.params.sessionId;
    if (!sessionId) {
      return res.status(400).json({ success: false, error: 'sessionId é obrigatório' });
    }

    console.log(`🔄 Reconectando sessão ${sessionId}...`);

    if (sessions.has(sessionId)) {
      const session = sessions.get(sessionId);
      if (session.sock) session.sock.end();
      if (session.backupInterval) clearInterval(session.backupInterval);
      sessions.delete(sessionId);
    }

    setTimeout(() => connectToWhatsApp(sessionId), 1000);

    res.json({
      success: true,
      message: `Reconexão iniciada para sessão ${sessionId}`,
      session_id: sessionId,
    });
  } catch (error) {
    console.error('❌ Erro ao reconectar sessão:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      session_id: req.params.sessionId,
    });
  }
});

// Limpar sessão específica (APAGA credenciais locais!)
app.post('/clear-session/:sessionId', async (req, res) => {
  try {
    const sessionId = req.params.sessionId;
    if (!sessionId) {
      return res.status(400).json({ success: false, error: 'sessionId é obrigatório' });
    }

    console.log(`🧹 Limpando sessão ${sessionId}...`);

    if (sessions.has(sessionId)) {
      const session = sessions.get(sessionId);
      if (session.sock) session.sock.end();
      if (session.backupInterval) clearInterval(session.backupInterval);
      sessions.delete(sessionId);
    }

    const authPath = getAuthPath(sessionId);
    if (fs.existsSync(authPath)) fs.rmSync(authPath, { recursive: true, force: true });

    res.json({ success: true, message: `Sessão ${sessionId} limpa com sucesso`, session_id: sessionId });
  } catch (error) {
    console.error('❌ Erro ao limpar sessão:', error);
    res.status(500).json({ success: false, error: error.message, session_id: req.params.sessionId });
  }
});

// Listar todas as sessões ativas
app.get('/sessions', (req, res) => {
  try {
    const sessionsData = [];

    for (const [sessionId, session] of sessions.entries()) {
      sessionsData.push({
        session_id: sessionId,
        connected: session.isConnected,
        status: session.status,
        qr_available: session.qrCode !== '',
        phone_number: session.sock?.user?.id || null,
        last_seen: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      total_sessions: sessionsData.length,
      sessions: sessionsData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('❌ Erro ao listar sessões:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// ===== ENDPOINTS DE COMPATIBILIDADE (?sessionId=...) =====
app.get('/status', (req, res) => {
  const sessionId = req.query.sessionId;
  if (!sessionId) {
    return res.status(400).json({
      connected: false,
      status: 'error',
      error: 'sessionId é obrigatório no query parameter (?sessionId=user_123)',
      qr_available: false,
      timestamp: new Date().toISOString(),
    });
  }

  const session = sessions.get(sessionId);
  if (!session) {
    return res.json({
      connected: false,
      status: 'not_initialized',
      session: null,
      qr_available: false,
      timestamp: new Date().toISOString(),
      session_id: sessionId,
    });
  }

  res.json({
    connected: session.isConnected,
    status: session.status,
    session: session.sock?.user?.id || null,
    qr_available: session.qrCode !== '',
    timestamp: new Date().toISOString(),
    session_id: sessionId,
  });
});

app.get('/qr', async (req, res) => {
  const sessionId = req.query.sessionId;
  if (!sessionId) {
    return res.status(400).json({
      success: false,
      error: 'sessionId é obrigatório no query parameter (?sessionId=user_123)',
    });
  }

  try {
    if (!sessions.has(sessionId)) {
      await connectToWhatsApp(sessionId);
      await new Promise((r) => setTimeout(r, 2500));
    }

    const session = sessions.get(sessionId);
    if (!session || !session.qrCode) {
      return res.status(404).json({
        success: false,
        error: `QR Code não disponível para sessão ${sessionId}. Tente reconectar.`,
        session_id: sessionId,
      });
    }

    const qrImage = await QRCode.toDataURL(session.qrCode);

    res.json({
      success: true,
      qr: session.qrCode,
      qr_image: qrImage,
      instructions: 'Abra WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho',
      session_id: sessionId,
    });
  } catch (error) {
    console.error('❌ Erro ao gerar QR:', error);
    res.status(500).json({
      success: false,
      error: 'Erro ao gerar QR Code',
      session_id: sessionId,
    });
  }
});

// ===== AUTO-RESTAURAR SESSÕES LOCAIS NA INICIALIZAÇÃO =====
function autoRestoreLocalSessions() {
  try {
    console.log('🔄 Vasculhando sessões locais para auto-restauração...');
    const entries = fs.readdirSync(AUTH_BASE_DIR, { withFileTypes: true });

    const folders = entries
      .filter((e) => e.isDirectory() && e.name.startsWith('auth_info_'))
      .map((e) => e.name);

    if (folders.length === 0) {
      console.log('📭 Nenhuma sessão local encontrada');
      return;
    }

    console.log(`🗂️  Encontradas ${folders.length} pastas de sessão local`);
    folders.forEach((dirName, idx) => {
      const sessionId = dirName.replace('auth_info_', '');
      console.log(`🔄 Restaurando sessão local: ${sessionId}`);
      setTimeout(() => connectToWhatsApp(sessionId), 1500 * idx); // espaça as conexões
    });
  } catch (err) {
    console.log('⚠️ Erro ao procurar sessões locais:', err.message);
  }
}

// Inicializar servidor
app.listen(PORT, () => {
  console.log('🚀 Baileys API rodando na porta', PORT);
  console.log('📦 AUTH_BASE_DIR:', AUTH_BASE_DIR);
  console.log('📱 Status: http://localhost:' + PORT + '/status?sessionId=SEU_ID');
  console.log('🔗 QR Code: http://localhost:' + PORT + '/qr?sessionId=SEU_ID');
  console.log('📋 Endpoints: GET /status/:sessionId, GET /qr/:sessionId, POST /send-message, POST /reconnect/:sessionId, POST /clear-session/:sessionId, GET /sessions');
  console.log('🔥 CADA USUÁRIO DEVE TER SUA PRÓPRIA SESSÃO! Ex.: /qr/user_1460561546');

  // Auto-restaurar sessões locais após 2s
  setTimeout(autoRestoreLocalSessions, 2000);
});

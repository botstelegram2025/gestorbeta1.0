const { DisconnectReason, default: makeWASocket, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const express = require('express');
const QRCode = require('qrcode');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = 3000;

// Middlewares
app.use(cors());
app.use(express.json());

// Estado global para múltiplas sessões
const sessions = new Map(); // sessionId -> { sock, qrCode, isConnected, status, backupInterval }
const SESSIONS_DIR = process.env.SESSIONS_DIR || path.join(__dirname, 'sessions');
if (!fs.existsSync(SESSIONS_DIR)) { fs.mkdirSync(SESSIONS_DIR, { recursive: true }); }

let defaultSessionId = 'default';

// Sistema de backup da sessão para PostgreSQL (por sessão específica)
const saveSessionToDatabase = async (sessionId) => {
    try {
        const authPath = `./auth_info_${sessionId}`;
        if (!fs.existsSync(authPath)) return;

        const files = fs.readdirSync(authPath);
        const sessionData = {};
        
        for (const file of files) {
            if (file.endsWith('.json')) {
                const filePath = path.join(authPath, file);
                const content = fs.readFileSync(filePath, 'utf8');
                sessionData[file] = content;
            }
        }

        // Salvar no banco via API Python com ID da sessão
        if (Object.keys(sessionData).length > 0) {
            await fetch('http://localhost:5000/api/session/backup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    session_data: sessionData,
                    session_id: sessionId
                })
            });
            console.log(`💾 Sessão ${sessionId} salva no banco de dados`);
        }
    } catch (error) {
        console.log(`⚠️ Erro ao salvar sessão ${sessionId}:`, error.message);
    }
};

// Restaurar sessão do banco de dados (por sessão específica)
const restoreSessionFromDatabase = async (sessionId) => {
    try {
        const response = await fetch(`http://localhost:5000/api/session/restore?session_id=${sessionId}`);
        if (response.ok) {
            const { session_data } = await response.json();
            
            if (session_data && Object.keys(session_data).length > 0) {
                const authPath = `./auth_info_${sessionId}`;
                if (!fs.existsSync(authPath)) {
                    fs.mkdirSync(authPath, { recursive: true });
                }

                for (const [filename, content] of Object.entries(session_data)) {
                    const filePath = path.join(authPath, filename);
                    fs.writeFileSync(filePath, content);
                }
                
                console.log(`🔄 Sessão ${sessionId} restaurada do banco de dados`);
                return true;
            }
        }
    } catch (error) {
        console.log(`⚠️ Erro ao restaurar sessão ${sessionId}:`, error.message);
    }
    return false;
};

// Função para conectar ao WhatsApp (por sessão específica)
async function connectToWhatsApp(sessionId = defaultSessionId) {
const authPath = path.join(SESSIONS_DIR, String(sessionId));
const { state, saveCreds } = await useMultiFileAuthState(authPath);

    try {
        console.log(`🔄 Iniciando conexão com WhatsApp para sessão ${sessionId}...`);
        
        // Criar ou obter dados da sessão
        if (!sessions.has(sessionId)) {
            sessions.set(sessionId, {
                sock: null,
                qrCode: '',
                isConnected: false,
                status: 'disconnected',
                backupInterval: null
            });
        }
        
        const session = sessions.get(sessionId);
        
        // Primeiro tentar restaurar sessão do banco
        await restoreSessionFromDatabase(sessionId);
        
        const { state, saveCreds } = await useMultiFileAuthState(`./auth_info_${sessionId}`);
        
        session.sock = makeWASocket({ auth: state, printQRInTerminal: false, 
            auth: state,
            printQRInTerminal: false
        });

        // Salvar credenciais e backup automático
        session.sock.ev.on('creds.update', async () => {
            await saveCreds();
            // Fazer backup imediato a cada update das credenciais
            setTimeout(() => saveSessionToDatabase(sessionId), 1000);
        });
        
        // Monitorar conexão
        session.sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (connection !== session.status) {
                console.log(`📱 Sessão ${sessionId} - Status:`, connection);
            }
            
            if (qr) {
                console.log(`📱 QR Code gerado para sessão ${sessionId}!`);
                session.qrCode = qr;
                session.status = 'qr_ready';
            }
            
            if (connection === 'close') {
                session.isConnected = false;
                session.status = 'disconnected';
                
                const shouldReconnect = (lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
                console.log(`🔌 Sessão ${sessionId} - Conexão fechada. Reconectar?`, shouldReconnect);
                
                // Tratamento de reconexão específico por sessão
                if ((lastDisconnect?.error)?.output?.statusCode === DisconnectReason.badSession ||
                    (lastDisconnect?.error)?.output?.statusCode === DisconnectReason.restartRequired ||
                    lastDisconnect?.error?.message?.includes('device_removed') ||
                    lastDisconnect?.error?.message?.includes('conflict')) {
                    console.log(`🧹 Sessão ${sessionId} - Aguardando devido a conflito...`);
                    session.qrCode = '';
                    session.status = 'disconnected';
                    setTimeout(() => connectToWhatsApp(sessionId), 30000);
                } else if (shouldReconnect) {
                    setTimeout(() => connectToWhatsApp(sessionId), 10000);
                }
            } else if (connection === 'open') {
                session.isConnected = true;
                session.status = 'connected';
                session.qrCode = '';
                console.log(`✅ Sessão ${sessionId} - WhatsApp conectado!`);
                
                // Configurar backup automático
                if (session.backupInterval) clearInterval(session.backupInterval);
                session.backupInterval = setInterval(() => saveSessionToDatabase(sessionId), 2 * 60 * 1000);
                
                // Fazer backup imediato após conectar
                setTimeout(() => saveSessionToDatabase(sessionId), 5000);
                console.log(`📞 Sessão ${sessionId} - Número:`, session.sock.user.id);
            } else if (connection === 'connecting') {
                if (session.status !== 'connecting') {
                    session.status = 'connecting';
                    console.log(`🔄 Sessão ${sessionId} - Conectando...`);
                }
            } else if (connection === 'close') {
                const shouldReconnect = (lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
                session.isConnected = false;
                session.status = 'close';
                session.qrCode = '';
                
                console.log(`🔌 Sessão ${sessionId} - Conexão fechada. Reconectar? ${shouldReconnect}`);
                
                if (shouldReconnect) {
                    // Aguardar 3 segundos antes de reconectar
                    setTimeout(() => {
                        console.log(`🔄 Reconectando sessão ${sessionId} automaticamente...`);
                        connectToWhatsApp(sessionId);
                    }, 3000);
                }
            }
        });

    } catch (error) {
        console.error(`❌ Erro ao conectar sessão ${sessionId}:`, error);
        const session = sessions.get(sessionId);
        if (session) {
            session.status = 'error';
        }
    }
}

// Endpoints da API

// Status da API (com suporte a sessões específicas)
app.get('/status/:sessionId', (req, res) => {
    const sessionId = req.params.sessionId || defaultSessionId;
    const session = sessions.get(sessionId);
    
    if (!session) {
        return res.json({
            connected: false,
            status: 'not_initialized',
            session: null,
            qr_available: false,
            timestamp: new Date().toISOString(),
            session_id: sessionId
        });
    }
    
    res.json({
        connected: session.isConnected,
        status: session.status,
        session: session.sock?.user?.id || null,
        qr_available: session.qrCode !== '',
        timestamp: new Date().toISOString(),
        session_id: sessionId
    });
});

// Endpoints de compatibilidade sem parâmetros obrigatórios
app.get('/status', (req, res) => {
    const sessionId = req.query.sessionId || defaultSessionId;
    const session = sessions.get(sessionId);
    
    if (!session) {
        return res.json({
            connected: false,
            status: 'not_initialized',
            session: null,
            qr_available: false,
            timestamp: new Date().toISOString(),
            session_id: sessionId
        });
    }
    
    res.json({
        connected: session.isConnected,
        status: session.status,
        session: session.sock?.user?.id || null,
        qr_available: session.qrCode !== '',
        timestamp: new Date().toISOString(),
        session_id: sessionId
    });
});

app.get('/qr', async (req, res) => {
    try {
        const sessionId = req.query.sessionId || defaultSessionId;
        
        // Inicializar sessão se não existir
        if (!sessions.has(sessionId)) {
            await connectToWhatsApp(sessionId);
            // Aguardar um pouco para QR ser gerado
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
        
        const session = sessions.get(sessionId);
        
        if (!session || !session.qrCode) {
            return res.status(404).json({ 
                success: false, 
                error: `QR Code não disponível para sessão ${sessionId}. Tente reconectar.`,
                session_id: sessionId
            });
        }

        // Gerar imagem QR Code
        const qrImage = await QRCode.toDataURL(session.qrCode);
        
        res.json({
            success: true,
            qr: session.qrCode,
            qr_image: qrImage,
            instructions: 'Abra WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho',
            session_id: sessionId
        });
        
    } catch (error) {
        console.error('❌ Erro ao gerar QR:', error);
        res.status(500).json({ 
            success: false, 
            error: 'Erro ao gerar QR Code',
            session_id: req.query.sessionId || defaultSessionId
        });
    }
});

// Obter QR Code (com suporte a sessões específicas)
app.get('/qr/:sessionId', async (req, res) => {
    try {
        const sessionId = req.params.sessionId || defaultSessionId;
        
        // Inicializar sessão se não existir
        if (!sessions.has(sessionId)) {
            await connectToWhatsApp(sessionId);
            // Aguardar um pouco para QR ser gerado
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
        
        const session = sessions.get(sessionId);
        
        if (!session || !session.qrCode) {
            return res.status(404).json({ 
                success: false, 
                error: `QR Code não disponível para sessão ${sessionId}. Tente reconectar.`,
                session_id: sessionId
            });
        }

        // Gerar imagem QR Code
        const qrImage = await QRCode.toDataURL(session.qrCode);
        
        res.json({
            success: true,
            qr: session.qrCode,
            qr_image: qrImage,
            instructions: 'Abra WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho',
            session_id: sessionId
        });
        
    } catch (error) {
        console.error('❌ Erro ao gerar QR:', error);
        res.status(500).json({ 
            success: false, 
            error: 'Erro ao gerar QR Code',
            session_id: req.params.sessionId || defaultSessionId
        });
    }
});

// Enviar mensagem (com suporte a sessões específicas)
app.post('/send-message', async (req, res) => {
    try {
        const { number, message, session_id } = req.body;
        const sessionId = session_id || defaultSessionId;
        
        if (!number || !message) {
            return res.status(400).json({
                success: false,
                error: 'Número e mensagem são obrigatórios'
            });
        }
        
        const session = sessions.get(sessionId);
        
        if (!session || !session.isConnected) {
            return res.status(400).json({
                success: false,
                error: `WhatsApp não conectado para sessão ${sessionId}`,
                session_id: sessionId
            });
        }
        
        // Formatar número
        const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
        
        // Enviar mensagem
        const result = await session.sock.sendMessage(jid, { text: message });
        
        console.log(`✅ Mensagem enviada via sessão ${sessionId}:`, number, message.substring(0, 50) + '...');
        
        res.json({
            success: true,
            messageId: result.key.id,
            timestamp: new Date().toISOString(),
            session_id: sessionId
        });
        
    } catch (error) {
        console.error(`❌ Erro ao enviar mensagem via sessão ${sessionId}:`, error);
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: sessionId
        });
    }
});

// Reconectar (com suporte a sessões específicas)
app.post('/reconnect/:sessionId', async (req, res) => {
    try {
        const sessionId = req.params.sessionId || defaultSessionId;
        console.log(`🔄 Reconectando sessão ${sessionId}...`);
        
        // Limpar sessão existente
        if (sessions.has(sessionId)) {
            const session = sessions.get(sessionId);
            if (session.sock) {
                session.sock.end();
            }
            if (session.backupInterval) {
                clearInterval(session.backupInterval);
            }
            sessions.delete(sessionId);
        }
        
        // Iniciar nova conexão
        setTimeout(() => connectToWhatsApp(sessionId), 1000);
        
        res.json({
            success: true,
            message: `Reconexão iniciada para sessão ${sessionId}`,
            session_id: sessionId
        });
        
    } catch (error) {
        console.error(`❌ Erro ao reconectar sessão ${sessionId}:`, error);
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: sessionId
        });
    }
});

// Limpar sessão específica
app.post('/clear-session/:sessionId', async (req, res) => {
    try {
        const sessionId = req.params.sessionId || defaultSessionId;
        console.log(`🧹 Limpando sessão ${sessionId}...`);
        
        if (sessions.has(sessionId)) {
            const session = sessions.get(sessionId);
            if (session.sock) {
                session.sock.end();
            }
            if (session.backupInterval) {
                clearInterval(session.backupInterval);
            }
            sessions.delete(sessionId);
        }
        
        // Limpar auth_info específico da sessão
        const authPath = `./auth_info_${sessionId}`;
        if (fs.existsSync(authPath)) {
            fs.rmSync(authPath, { recursive: true });
        }
        
        res.json({
            success: true,
            message: `Sessão ${sessionId} limpa com sucesso`,
            session_id: sessionId
        });
        
    } catch (error) {
        console.error(`❌ Erro ao limpar sessão ${sessionId}:`, error);
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: sessionId
        });
    }
});

// Endpoint de reconectar compatível
app.post('/reconnect', async (req, res) => {
    try {
        const sessionId = req.body.sessionId || req.query.sessionId || defaultSessionId;
        console.log(`🔄 Reconectando sessão ${sessionId}...`);
        
        // Limpar sessão existente
        if (sessions.has(sessionId)) {
            const session = sessions.get(sessionId);
            if (session.sock) {
                session.sock.end();
            }
            if (session.backupInterval) {
                clearInterval(session.backupInterval);
            }
            sessions.delete(sessionId);
        }
        
        // Iniciar nova conexão
        setTimeout(() => connectToWhatsApp(sessionId), 1000);
        
        res.json({
            success: true,
            message: `Reconexão iniciada para sessão ${sessionId}`,
            session_id: sessionId
        });
        
    } catch (error) {
        console.error(`❌ Erro ao reconectar sessão ${sessionId}:`, error);
        res.status(500).json({
            success: false,
            error: error.message,
            session_id: sessionId
        });
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
                last_seen: new Date().toISOString()
            });
        }
        
        res.json({
            success: true,
            total_sessions: sessionsData.length,
            sessions: sessionsData,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('❌ Erro ao listar sessões:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Health check
app.get('/', (req, res) => {
    res.json({
        service: 'Baileys API Multi-Session',
        status: 'running',
        total_sessions: sessions.size,
        timestamp: new Date().toISOString()
    });
});

// Iniciar servidor
// Pré-carrega sessões existentes do disco (opcional)
async function preloadSessions() {
    try {
        const dirs = fs.readdirSync(SESSIONS_DIR, { withFileTypes: true })
            .filter(d => d.isDirectory())
            .map(d => d.name);
        for (const sid of dirs) {
            if (!sessions.has(sid)) {
                console.log(`🔁 Restaurando sessão persistida: ${sid}`);
                try {
                    await connectToWhatsApp(sid);
                } catch (e) {
                    console.error(`Falha ao restaurar sessão ${sid}:`, e?.message || e);
                }
            }
        }
    } catch (e) {
        console.warn("Não foi possível listar SESSIONS_DIR para preload:", e?.message || e);
    }
}

preloadSessions();

app.listen(PORT, () => {
    console.log(`🚀 Baileys API rodando na porta ${PORT}`);
    console.log(`📱 Status: http://localhost:${PORT}/status`);
    console.log(`🔗 QR Code: http://localhost:${PORT}/qr`);
    console.log('');
    
    // Inicializar sistema multi-sessão
    console.log('📱 Sistema multi-sessão Baileys inicializado');
    console.log('📋 Endpoints disponíveis:');
    console.log('   GET  /status/:sessionId - Status da sessão');
    console.log('   GET  /qr/:sessionId - QR Code da sessão');
    console.log('   POST /send-message - Enviar mensagem');
    console.log('   POST /reconnect/:sessionId - Reconectar sessão');
    console.log('   POST /clear-session/:sessionId - Limpar sessão');
    console.log('   GET  /sessions - Listar todas as sessões');
    console.log('');
});

// Tratamento de erros
process.on('uncaughtException', (error) => {
    console.error('❌ Erro não tratado:', error);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Promise rejeitada:', reason);
});
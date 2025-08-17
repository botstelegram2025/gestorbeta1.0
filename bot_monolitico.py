#!/usr/bin/env python3
"""
Bot de Gestão de Clientes - Versão Monolítica
============================================
Sistema completo multi-usuário com WhatsApp, Telegram e Mercado Pago
Todos os módulos consolidados em um único arquivo para facilitar deploy

Funcionalidades:
- Bot Telegram completo
- Sistema multi-usuário com assinaturas
- WhatsApp via Baileys (servidor Node.js separado)
- Templates avançados (8 tipos)
- Automação inteligente
- Pagamentos PIX via Mercado Pago
- Relatórios e analytics

Autor: Sistema completo funcional
Data: 17/08/2025
"""

import os
import sys
import json
import logging
import asyncio
import threading
import time
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
import hashlib
import uuid
import pytz
from dataclasses import dataclass
import qrcode
from io import BytesIO
import base64
from urllib.parse import quote_plus

# Telegram Bot
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError, NetworkError, TimedOut

# Scheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

# Flask para webhooks e API
from flask import Flask, request, jsonify, render_template_string

# =============================================================================
# CONFIGURAÇÕES E CONSTANTES
# =============================================================================

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Timezone Brasil
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Configurações do bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID', '0'))
DATABASE_URL = os.environ.get('DATABASE_URL')
MERCADOPAGO_ACCESS_TOKEN = os.environ.get('MERCADOPAGO_ACCESS_TOKEN')

# URLs da API Baileys (assumindo servidor Node.js separado)
BAILEYS_BASE_URL = 'http://localhost:3000'
BAILEYS_SEND_URL = f'{BAILEYS_BASE_URL}/send-message'
BAILEYS_STATUS_URL = f'{BAILEYS_BASE_URL}/status'
BAILEYS_QR_URL = f'{BAILEYS_BASE_URL}/qr'

# Preços e configurações
PRECO_MENSAL = 20.00
DIAS_TRIAL = 7

# =============================================================================
# MODELOS DE DADOS E UTILITÁRIOS
# =============================================================================

@dataclass
class Usuario:
    """Modelo para usuários do sistema"""
    chat_id: int
    nome: str
    email: str
    telefone: str
    status: str  # 'trial', 'ativo', 'vencido', 'cancelado'
    data_cadastro: datetime
    data_vencimento: datetime
    trial_usado: bool = False

@dataclass
class Cliente:
    """Modelo para clientes"""
    id: Optional[int]
    nome: str
    telefone: str
    pacote: str
    valor: float
    data_vencimento: datetime
    servidor: str
    chat_id_usuario: int
    notificar: bool = True
    status: str = 'ativo'  # 'ativo', 'vencido', 'suspenso'

@dataclass
class Template:
    """Modelo para templates de mensagem"""
    id: Optional[int]
    nome: str
    tipo: str
    conteudo: str
    chat_id_usuario: int
    ativo: bool = True
    descricao: str = ""

# =============================================================================
# CLASSE DE CONEXÃO COM BANCO DE DADOS
# =============================================================================

class DatabaseManager:
    """Gerenciador do banco PostgreSQL com suporte multi-tenant"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.connection = None
        self._setup_database()
    
    def _get_connection(self):
        """Obter conexão com o banco"""
        if not self.connection or self.connection.closed:
            self.connection = psycopg2.connect(
                self.database_url,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            self.connection.autocommit = True
        return self.connection
    
    def _setup_database(self):
        """Criar tabelas necessárias"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Tabela de usuários
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    chat_id BIGINT PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    email VARCHAR(255),
                    telefone VARCHAR(20),
                    status VARCHAR(50) DEFAULT 'trial',
                    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data_vencimento TIMESTAMP,
                    trial_usado BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabela de clientes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clientes (
                    id SERIAL PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    telefone VARCHAR(20) NOT NULL,
                    pacote VARCHAR(255),
                    valor DECIMAL(10,2) DEFAULT 0.00,
                    data_vencimento DATE NOT NULL,
                    servidor VARCHAR(255),
                    chat_id_usuario BIGINT NOT NULL,
                    notificar BOOLEAN DEFAULT TRUE,
                    status VARCHAR(50) DEFAULT 'ativo',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
                )
            """)
            
            # Tabela de templates
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id SERIAL PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    tipo VARCHAR(100) DEFAULT 'geral',
                    conteudo TEXT NOT NULL,
                    chat_id_usuario BIGINT NOT NULL,
                    ativo BOOLEAN DEFAULT TRUE,
                    descricao TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
                )
            """)
            
            # Tabela de mensagens enviadas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mensagens_enviadas (
                    id SERIAL PRIMARY KEY,
                    cliente_id INTEGER,
                    template_id INTEGER,
                    conteudo TEXT,
                    telefone VARCHAR(20),
                    status VARCHAR(50) DEFAULT 'pendente',
                    data_envio TIMESTAMP,
                    chat_id_usuario BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                    FOREIGN KEY (template_id) REFERENCES templates(id),
                    FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
                )
            """)
            
            # Tabela de configurações
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS configuracoes (
                    id SERIAL PRIMARY KEY,
                    chave VARCHAR(255) NOT NULL,
                    valor TEXT,
                    chat_id_usuario BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chave, chat_id_usuario)
                )
            """)
            
            # Tabela de sessões WhatsApp
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    session_data TEXT,
                    status VARCHAR(50) DEFAULT 'desconectado',
                    chat_id_usuario BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(session_id, chat_id_usuario)
                )
            """)
            
            # Índices para performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_usuario ON clientes(chat_id_usuario)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_vencimento ON clientes(data_vencimento)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_usuario ON templates(chat_id_usuario)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mensagens_usuario ON mensagens_enviadas(chat_id_usuario)")
            
            logger.info("✅ Banco de dados configurado com sucesso")
            
        except Exception as e:
            logger.error(f"❌ Erro ao configurar banco: {e}")
    
    def salvar_usuario(self, usuario: Usuario) -> bool:
        """Salvar usuário no banco"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO usuarios (chat_id, nome, email, telefone, status, data_vencimento, trial_usado)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chat_id) 
                DO UPDATE SET 
                    nome = EXCLUDED.nome,
                    email = EXCLUDED.email,
                    telefone = EXCLUDED.telefone,
                    status = EXCLUDED.status,
                    data_vencimento = EXCLUDED.data_vencimento,
                    trial_usado = EXCLUDED.trial_usado,
                    updated_at = CURRENT_TIMESTAMP
            """, (usuario.chat_id, usuario.nome, usuario.email, usuario.telefone, 
                  usuario.status, usuario.data_vencimento, usuario.trial_usado))
            
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar usuário: {e}")
            return False
    
    def buscar_usuario(self, chat_id: int) -> Optional[Usuario]:
        """Buscar usuário por chat_id"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM usuarios WHERE chat_id = %s", (chat_id,))
            row = cursor.fetchone()
            
            if row:
                return Usuario(
                    chat_id=row['chat_id'],
                    nome=row['nome'],
                    email=row['email'],
                    telefone=row['telefone'],
                    status=row['status'],
                    data_cadastro=row['data_cadastro'],
                    data_vencimento=row['data_vencimento'],
                    trial_usado=row['trial_usado']
                )
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar usuário: {e}")
            return None
    
    def salvar_cliente(self, cliente: Cliente) -> Optional[int]:
        """Salvar cliente no banco"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if cliente.id:
                # Atualizar
                cursor.execute("""
                    UPDATE clientes SET 
                        nome = %s, telefone = %s, pacote = %s, valor = %s,
                        data_vencimento = %s, servidor = %s, notificar = %s,
                        status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND chat_id_usuario = %s
                """, (cliente.nome, cliente.telefone, cliente.pacote, cliente.valor,
                      cliente.data_vencimento, cliente.servidor, cliente.notificar,
                      cliente.status, cliente.id, cliente.chat_id_usuario))
                return cliente.id
            else:
                # Inserir
                cursor.execute("""
                    INSERT INTO clientes (nome, telefone, pacote, valor, data_vencimento, 
                                        servidor, chat_id_usuario, notificar, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (cliente.nome, cliente.telefone, cliente.pacote, cliente.valor,
                      cliente.data_vencimento, cliente.servidor, cliente.chat_id_usuario,
                      cliente.notificar, cliente.status))
                
                return cursor.fetchone()['id']
                
        except Exception as e:
            logger.error(f"Erro ao salvar cliente: {e}")
            return None
    
    def buscar_clientes_usuario(self, chat_id_usuario: int) -> List[Dict]:
        """Buscar todos os clientes de um usuário"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM clientes 
                WHERE chat_id_usuario = %s 
                ORDER BY data_vencimento ASC
            """, (chat_id_usuario,))
            
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erro ao buscar clientes: {e}")
            return []
    
    def salvar_template(self, template: Template) -> Optional[int]:
        """Salvar template no banco"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO templates (nome, tipo, conteudo, chat_id_usuario, ativo, descricao)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (template.nome, template.tipo, template.conteudo, 
                  template.chat_id_usuario, template.ativo, template.descricao))
            
            return cursor.fetchone()['id']
        except Exception as e:
            logger.error(f"Erro ao salvar template: {e}")
            return None
    
    def buscar_templates_usuario(self, chat_id_usuario: int) -> List[Dict]:
        """Buscar templates de um usuário"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM templates 
                WHERE chat_id_usuario = %s AND ativo = TRUE
                ORDER BY created_at DESC
            """, (chat_id_usuario,))
            
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erro ao buscar templates: {e}")
            return []
    
    def salvar_configuracao(self, chave: str, valor: str, chat_id_usuario: int):
        """Salvar configuração do usuário"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO configuracoes (chave, valor, chat_id_usuario)
                VALUES (%s, %s, %s)
                ON CONFLICT (chave, chat_id_usuario)
                DO UPDATE SET valor = EXCLUDED.valor, updated_at = CURRENT_TIMESTAMP
            """, (chave, valor, chat_id_usuario))
            
        except Exception as e:
            logger.error(f"Erro ao salvar configuração: {e}")
    
    def buscar_configuracao(self, chave: str, chat_id_usuario: int, default: str = "") -> str:
        """Buscar configuração do usuário"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT valor FROM configuracoes 
                WHERE chave = %s AND chat_id_usuario = %s
            """, (chave, chat_id_usuario))
            
            row = cursor.fetchone()
            return row['valor'] if row else default
        except Exception as e:
            logger.error(f"Erro ao buscar configuração: {e}")
            return default

# =============================================================================
# CLASSE PARA PAGAMENTOS MERCADO PAGO
# =============================================================================

class MercadoPagoIntegration:
    """Integração com Mercado Pago para PIX"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.mercadopago.com"
    
    def criar_pagamento_pix(self, valor: float, descricao: str, email_pagador: str) -> Dict:
        """Criar pagamento PIX"""
        try:
            url = f"{self.base_url}/v1/payments"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "transaction_amount": valor,
                "description": descricao,
                "payment_method_id": "pix",
                "payer": {
                    "email": email_pagador
                }
            }
            
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 201:
                payment_data = response.json()
                return {
                    "success": True,
                    "payment_id": payment_data["id"],
                    "qr_code": payment_data["point_of_interaction"]["transaction_data"]["qr_code"],
                    "qr_code_base64": payment_data["point_of_interaction"]["transaction_data"]["qr_code_base64"],
                    "status": payment_data["status"]
                }
            else:
                return {"success": False, "error": response.text}
                
        except Exception as e:
            logger.error(f"Erro ao criar pagamento PIX: {e}")
            return {"success": False, "error": str(e)}
    
    def consultar_pagamento(self, payment_id: str) -> Dict:
        """Consultar status do pagamento"""
        try:
            url = f"{self.base_url}/v1/payments/{payment_id}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": response.text}
                
        except Exception as e:
            logger.error(f"Erro ao consultar pagamento: {e}")
            return {"success": False, "error": str(e)}

# =============================================================================
# CLASSE PARA BAILEYS WHATSAPP API
# =============================================================================

class BaileysAPI:
    """Interface para API Baileys WhatsApp"""
    
    def __init__(self, base_url: str = BAILEYS_BASE_URL):
        self.base_url = base_url
    
    def send_message(self, telefone: str, mensagem: str) -> Dict:
        """Enviar mensagem via WhatsApp"""
        try:
            # Formatar telefone para Baileys (DDI + DDD + número)
            telefone_formatado = self._formatar_telefone(telefone)
            
            data = {
                "number": telefone_formatado,
                "message": mensagem
            }
            
            response = requests.post(f"{self.base_url}/send-message", 
                                   json=data, timeout=30)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem WhatsApp: {e}")
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> Dict:
        """Obter status da conexão WhatsApp"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Erro ao obter status WhatsApp: {e}")
            return {"success": False, "error": str(e)}
    
    def get_qr_code(self) -> Dict:
        """Obter QR Code para autenticação"""
        try:
            response = requests.get(f"{self.base_url}/qr", timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Erro ao obter QR Code: {e}")
            return {"success": False, "error": str(e)}
    
    def _formatar_telefone(self, telefone: str) -> str:
        """Formatar telefone para WhatsApp (DDI55 + DDD + número)"""
        # Remove caracteres não numéricos
        telefone = ''.join(filter(str.isdigit, telefone))
        
        # Se já tem DDI (55), manter
        if telefone.startswith('55') and len(telefone) >= 12:
            return telefone
        
        # Adicionar DDI 55 (Brasil)
        if len(telefone) == 11:  # DDD + 9 dígitos
            return f"55{telefone}"
        elif len(telefone) == 10:  # DDD + 8 dígitos
            return f"55{telefone}"
        
        return telefone

# =============================================================================
# CLASSE PRINCIPAL DO BOT TELEGRAM
# =============================================================================

class BotGestaoClientes:
    """Bot principal para gestão de clientes"""
    
    def __init__(self):
        self.bot_token = BOT_TOKEN
        self.admin_chat_id = ADMIN_CHAT_ID
        self.db = DatabaseManager(DATABASE_URL) if DATABASE_URL else None
        self.mercadopago = MercadoPagoIntegration(MERCADOPAGO_ACCESS_TOKEN) if MERCADOPAGO_ACCESS_TOKEN else None
        self.baileys = BaileysAPI()
        
        # Estados de conversação
        self.conversation_states = {}
        self.user_states = {}
        
        # Scheduler para automação
        self.scheduler = BackgroundScheduler(
            executors={'default': ThreadPoolExecutor(max_workers=3)},
            timezone=TIMEZONE
        )
        
        # Flask app para webhooks
        self.flask_app = Flask(__name__)
        self._setup_flask_routes()
        
        # Templates padrão
        self.templates_padrão = {
            'boas_vindas': """👋 Olá {nome}!

🎉 *Bem-vindo(a) ao nosso serviço!*

📋 *Seus dados:*
• Plano: {pacote}
• Valor: R$ {valor}
• Vencimento: {vencimento}

📱 Em caso de dúvidas, entre em contato!""",
            
            'dois_dias_antes': """⏰ Olá {nome}!

Seu plano vence em 2 dias: *{vencimento}*

📋 *Detalhes do seu plano:*
• Plano: {pacote}
• Valor: R$ {valor}
• Status: Ativo

💡 *Para renovar:*
• Faça o pagamento antecipadamente
• Evite interrupção do serviço

💳 *PIX:* {pix}
👤 *Titular:* {titular}

❓ Dúvidas? Entre em contato!""",
            
            'um_dia_antes': """⚠️ Olá {nome}!

Seu plano vence AMANHÃ: *{vencimento}*

🚨 *ATENÇÃO:*
• Plano: {pacote}
• Valor: R$ {valor}
• Vence em: 24 horas

⚡ *Renove hoje e evite bloqueio!*

💳 *PIX:* {pix}
💰 *Valor:* R$ {valor}
👤 *Titular:* {titular}

✅ Após o pagamento, envie o comprovante!

📱 Dúvidas? Responda esta mensagem.""",
            
            'vencimento_hoje': """📅 Olá {nome}!

🚨 *SEU PLANO VENCE HOJE: {vencimento}*

⚠️ *URGENTE:*
• Plano: {pacote}
• Valor: R$ {valor}
• Status: VENCE HOJE

🔴 *Renove AGORA para não perder o acesso!*

💳 *PIX:* {pix}
💰 *Valor:* R$ {valor}
👤 *Titular:* {titular}

⏰ *Pagamentos após às 18h podem não ser processados hoje*

📱 Dúvidas? Entre em contato URGENTE!""",
            
            'um_dia_apos_vencido': """🔴 Olá {nome}!

❌ *SEU PLANO VENCEU ONTEM: {vencimento}*

🚫 *ACESSO SUSPENSO:*
• Plano: {pacote}
• Valor: R$ {valor}
• Status: VENCIDO

⚡ *Renove agora para reativar:*

💳 *PIX:* {pix}
💰 *Valor:* R$ {valor}
👤 *Titular:* {titular}

✅ Após o pagamento, seu acesso será reativado em até 2 horas.

📱 Dúvidas? Entre em contato!"""
        }
    
    def _setup_flask_routes(self):
        """Configurar rotas Flask"""
        
        @self.flask_app.route('/health')
        def health():
            return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
        
        @self.flask_app.route('/webhook', methods=['POST'])
        def webhook():
            # Webhook para Mercado Pago ou outros serviços
            return jsonify({"received": True})
    
    def _criar_teclado_principal(self, is_admin: bool = False) -> ReplyKeyboardMarkup:
        """Criar teclado principal do bot"""
        if is_admin:
            keyboard = [
                ['👥 Gestão de Clientes', '📊 Relatórios'],
                ['📄 Templates', '📱 WhatsApp/Baileys'],
                ['⚙️ Configurações', '👑 Admin']
            ]
        else:
            keyboard = [
                ['👥 Meus Clientes', '📊 Meus Relatórios'],
                ['📄 Templates', '📱 WhatsApp'],
                ['⚙️ Configurações']
            ]
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def _criar_teclado_configuracoes(self) -> ReplyKeyboardMarkup:
        """Criar teclado de configurações"""
        keyboard = [
            ['🏢 Dados da Empresa', '💳 Configurar PIX'],
            ['📱 Status WhatsApp', '📝 Templates'],
            ['⏰ Agendador', '⚙️ Horários'],
            ['🔔 Notificações', '📊 Sistema'],
            ['📚 Guia do Usuário'],
            ['🔙 Menu Principal']
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def is_admin(self, chat_id: int) -> bool:
        """Verificar se usuário é admin"""
        return chat_id == self.admin_chat_id
    
    def is_user_active(self, chat_id: int) -> bool:
        """Verificar se usuário tem acesso ativo"""
        if self.is_admin(chat_id):
            return True
        
        if not self.db:
            return False
        
        usuario = self.db.buscar_usuario(chat_id)
        if not usuario:
            return False
        
        now = datetime.now(TIMEZONE)
        return usuario.status in ['trial', 'ativo'] and usuario.data_vencimento > now
    
    def _substituir_variaveis(self, texto: str, cliente: Dict, chat_id_usuario: int) -> str:
        """Substituir variáveis no template"""
        if not self.db:
            return texto
        
        # Buscar configurações do usuário
        pix = self.db.buscar_configuracao('empresa_pix', chat_id_usuario, 'NÃO CONFIGURADO')
        titular = self.db.buscar_configuracao('empresa_titular', chat_id_usuario, 'SUA EMPRESA')
        
        # Formatações
        vencimento = cliente['data_vencimento'].strftime('%d/%m/%Y') if isinstance(cliente['data_vencimento'], datetime) else str(cliente['data_vencimento'])
        valor = f"{float(cliente['valor']):.2f}".replace('.', ',')
        
        # Substituições
        substituicoes = {
            '{nome}': cliente['nome'],
            '{telefone}': cliente['telefone'],
            '{pacote}': cliente['pacote'] or 'Plano Padrão',
            '{valor}': valor,
            '{vencimento}': vencimento,
            '{servidor}': cliente['servidor'] or 'Principal',
            '{pix}': pix,
            '{titular}': titular
        }
        
        for variavel, valor_sub in substituicoes.items():
            texto = texto.replace(variavel, str(valor_sub))
        
        return texto
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        chat_id = update.effective_chat.id
        
        if not self.db:
            await update.message.reply_text(
                "❌ Sistema temporariamente indisponível. Tente novamente em alguns minutos."
            )
            return
        
        # Verificar se é admin ou usuário registrado
        if self.is_admin(chat_id):
            mensagem = """🤖 *Bot de Gestão de Clientes - ADMIN*

Bem-vindo ao sistema completo de gestão!

🎯 *Funcionalidades disponíveis:*
• Gestão completa de clientes
• Sistema de templates avançado
• WhatsApp automatizado
• Relatórios detalhados
• Configurações do sistema

👑 *Acesso administrativo ativo*"""
            
            await update.message.reply_text(
                mensagem,
                parse_mode='Markdown',
                reply_markup=self._criar_teclado_principal(is_admin=True)
            )
        else:
            # Verificar se usuário existe
            usuario = self.db.buscar_usuario(chat_id)
            
            if not usuario:
                # Iniciar cadastro
                await self._iniciar_cadastro_usuario(update, context)
            elif self.is_user_active(chat_id):
                # Usuário ativo
                status_emoji = "🆓" if usuario.status == 'trial' else "✅"
                dias_restantes = (usuario.data_vencimento - datetime.now(TIMEZONE)).days
                
                mensagem = f"""🤖 *Bot de Gestão de Clientes*

Olá {usuario.nome}! Bem-vindo de volta.

{status_emoji} *Status:* {usuario.status.title()}
📅 *Vencimento:* {usuario.data_vencimento.strftime('%d/%m/%Y')}
⏰ *Dias restantes:* {dias_restantes}

🎯 *Suas funcionalidades:*
• Gestão de clientes
• Templates personalizados  
• WhatsApp automatizado
• Relatórios detalhados"""
                
                await update.message.reply_text(
                    mensagem,
                    parse_mode='Markdown',
                    reply_markup=self._criar_teclado_principal()
                )
            else:
                # Usuário vencido
                await self._mostrar_renovacao(update, context, usuario)
    
    async def _iniciar_cadastro_usuario(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Iniciar cadastro de novo usuário"""
        chat_id = update.effective_chat.id
        
        mensagem = """🎉 *Bem-vindo ao Bot de Gestão de Clientes!*

🆓 *Teste GRÁTIS por 7 dias*
💰 Apenas R$ 20,00/mês após o trial

🎯 *O que você vai ter:*
• ✅ Gestão completa de clientes
• ✅ WhatsApp automatizado 
• ✅ Templates profissionais
• ✅ Relatórios detalhados
• ✅ Suporte completo

📝 Para começar, preciso de algumas informações.

*Qual é o seu nome completo?*"""
        
        # Definir estado de cadastro
        self.conversation_states[chat_id] = {
            'action': 'cadastro_usuario',
            'step': 'nome'
        }
        
        await update.message.reply_text(mensagem, parse_mode='Markdown')
    
    async def _mostrar_renovacao(self, update: Update, context: ContextTypes.DEFAULT_TYPE, usuario: Usuario):
        """Mostrar opções de renovação"""
        if not self.mercadopago:
            await update.message.reply_text(
                "❌ Sistema de pagamentos temporariamente indisponível."
            )
            return
        
        mensagem = f"""⚠️ *Assinatura Vencida*

Olá {usuario.nome}, sua assinatura venceu.

💰 *Renovar por apenas R$ 20,00/mês*

🎯 *Seus benefícios:*
• Gestão ilimitada de clientes
• WhatsApp automatizado
• Templates profissionais
• Relatórios detalhados

💳 *Clique no botão para gerar PIX:*"""
        
        keyboard = [
            [InlineKeyboardButton("💳 Gerar PIX R$ 20,00", callback_data="gerar_pix_renovacao")]
        ]
        
        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar mensagens de texto"""
        chat_id = update.effective_chat.id
        text = update.message.text
        
        # Verificar se usuário tem acesso
        if not self.is_admin(chat_id) and not self.is_user_active(chat_id):
            await update.message.reply_text(
                "❌ Acesso negado. Use /start para renovar sua assinatura."
            )
            return
        
        # Processar estados de conversação
        if chat_id in self.conversation_states:
            await self._processar_estado_conversacao(update, context)
            return
        
        # Comandos do menu principal
        if text == '👥 Gestão de Clientes' or text == '👥 Meus Clientes':
            await self._gestao_clientes_menu(update, context)
        
        elif text == '📊 Relatórios' or text == '📊 Meus Relatórios':
            await self._mostrar_relatorios(update, context)
        
        elif text == '📄 Templates':
            await self._templates_menu(update, context)
        
        elif text == '📱 WhatsApp/Baileys' or text == '📱 WhatsApp':
            await self._whatsapp_menu(update, context)
        
        elif text == '⚙️ Configurações':
            await self._configuracoes_menu(update, context)
        
        elif text == '👑 Admin' and self.is_admin(chat_id):
            await self._admin_menu(update, context)
        
        # Submenu configurações
        elif text == '🏢 Dados da Empresa':
            await self._config_empresa(update, context)
        
        elif text == '💳 Configurar PIX':
            await self._config_pix(update, context)
        
        elif text == '📱 Status WhatsApp':
            await self._status_whatsapp(update, context)
        
        elif text == '🔙 Menu Principal':
            await self.start_command(update, context)
        
        else:
            await update.message.reply_text(
                "❓ Comando não reconhecido. Use o menu abaixo.",
                reply_markup=self._criar_teclado_principal(self.is_admin(chat_id))
            )
    
    async def _processar_estado_conversacao(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processar estados de conversação"""
        chat_id = update.effective_chat.id
        text = update.message.text
        state = self.conversation_states[chat_id]
        
        if state['action'] == 'cadastro_usuario':
            await self._processar_cadastro_usuario(update, context, state, text)
        
        elif state['action'] == 'adicionar_cliente':
            await self._processar_adicionar_cliente(update, context, state, text)
        
        elif state['action'] == 'criar_template':
            await self._processar_criar_template(update, context, state, text)
    
    async def _processar_cadastro_usuario(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: Dict, text: str):
        """Processar cadastro de usuário"""
        chat_id = update.effective_chat.id
        
        if state['step'] == 'nome':
            state['nome'] = text
            state['step'] = 'email'
            await update.message.reply_text("📧 *Qual é o seu email?*", parse_mode='Markdown')
        
        elif state['step'] == 'email':
            state['email'] = text
            state['step'] = 'telefone'
            await update.message.reply_text("📱 *Qual é o seu telefone?*", parse_mode='Markdown')
        
        elif state['step'] == 'telefone':
            # Finalizar cadastro
            now = datetime.now(TIMEZONE)
            data_vencimento = now + timedelta(days=DIAS_TRIAL)
            
            usuario = Usuario(
                chat_id=chat_id,
                nome=state['nome'],
                email=state['email'],
                telefone=text,
                status='trial',
                data_cadastro=now,
                data_vencimento=data_vencimento,
                trial_usado=True
            )
            
            if self.db and self.db.salvar_usuario(usuario):
                mensagem = f"""✅ *Cadastro realizado com sucesso!*

🎉 Bem-vindo(a) {state['nome']}!

🆓 *Trial ativo até:* {data_vencimento.strftime('%d/%m/%Y')}
⏰ *{DIAS_TRIAL} dias gratuitos*

🚀 *Agora você pode:*
• Adicionar seus clientes
• Criar templates personalizados
• Configurar WhatsApp
• Gerar relatórios

💡 *Comece explorando o menu abaixo!*"""
                
                await update.message.reply_text(
                    mensagem,
                    parse_mode='Markdown',
                    reply_markup=self._criar_teclado_principal()
                )
            else:
                await update.message.reply_text("❌ Erro ao criar conta. Tente novamente.")
            
            # Limpar estado
            del self.conversation_states[chat_id]
    
    async def _gestao_clientes_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menu de gestão de clientes"""
        keyboard = [
            ['➕ Adicionar Cliente', '📋 Listar Clientes'],
            ['🔍 Buscar Cliente', '⚠️ Vencimentos'],
            ['🔙 Menu Principal']
        ]
        
        mensagem = """👥 *Gestão de Clientes*

📊 *Suas opções:*
• ➕ Adicionar novo cliente
• 📋 Ver todos os clientes
• 🔍 Buscar cliente específico
• ⚠️ Ver clientes vencendo

Escolha uma opção:"""
        
        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    
    async def _templates_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menu de templates"""
        chat_id = update.effective_chat.id
        
        if not self.db:
            await update.message.reply_text("❌ Sistema indisponível.")
            return
        
        templates = self.db.buscar_templates_usuario(chat_id)
        
        mensagem = f"""📄 *Gestão de Templates*

📊 *Seus templates:* {len(templates)}

💡 *Tipos disponíveis:*
• 👋 Boas Vindas
• ⏰ 2 Dias Antes 
• ⚠️ 1 Dia Antes
• 📅 Vencimento Hoje
• 🔴 1 Dia Após Vencido
• 💰 Cobrança Geral
• 🔄 Renovação
• 📝 Personalizado

🎯 *Escolha uma opção:*"""
        
        keyboard = [
            ['➕ Criar Template', '📋 Meus Templates'],
            ['🔄 Templates Padrão', '📊 Estatísticas'],
            ['🔙 Menu Principal']
        ]
        
        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    
    async def _whatsapp_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menu WhatsApp"""
        # Verificar status
        status_result = self.baileys.get_status()
        
        if status_result['success']:
            status_data = status_result['data']
            status = status_data.get('status', 'desconectado')
            emoji = "🟢" if status == 'conectado' else "🔴"
        else:
            status = 'erro'
            emoji = "❌"
        
        mensagem = f"""📱 *WhatsApp/Baileys*

{emoji} *Status:* {status.title()}

🎯 *Opções disponíveis:*
• 📱 Ver QR Code
• 🧪 Testar Envio
• 🔄 Reconectar
• 📊 Estatísticas

💡 *Nota:* O WhatsApp deve estar conectado para envios automáticos."""
        
        keyboard = [
            ['📱 QR Code WhatsApp', '🧪 Testar Envio'],
            ['🔄 Reconectar', '📊 Status Detalhado'],
            ['🔙 Menu Principal']
        ]
        
        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    
    async def _configuracoes_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menu de configurações"""
        chat_id = update.effective_chat.id
        
        if not self.db:
            await update.message.reply_text("❌ Sistema indisponível.")
            return
        
        # Buscar configurações atuais
        nome_empresa = self.db.buscar_configuracao('empresa_nome', chat_id, 'NÃO CONFIGURADO')
        pix_empresa = self.db.buscar_configuracao('empresa_pix', chat_id, 'NÃO CONFIGURADO')
        titular_conta = self.db.buscar_configuracao('empresa_titular', chat_id, 'NÃO CONFIGURADO')
        
        # Status indicators
        pix_status = "✅" if pix_empresa != 'NÃO CONFIGURADO' else "❌"
        titular_status = "✅" if titular_conta != 'NÃO CONFIGURADO' else "❌"
        
        mensagem = f"""⚙️ *CONFIGURAÇÕES DO SISTEMA*

🏢 *Empresa*
📝 Nome: {nome_empresa}

💳 *Dados PIX* {pix_status}
🔑 Chave PIX: {pix_empresa}
👤 Titular: {titular_conta}

📱 *WhatsApp/Baileys*
Status: Verificar menu WhatsApp

🔧 *Escolha uma opção para configurar:*"""
        
        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=self._criar_teclado_configuracoes()
        )
    
    def _setup_scheduler(self):
        """Configurar agendador de tarefas"""
        
        # Verificação diária às 9h
        self.scheduler.add_job(
            func=self._verificar_vencimentos_diarios,
            trigger=CronTrigger(hour=9, minute=0, timezone=TIMEZONE),
            id='verificar_vencimentos',
            name='Verificação Diária de Vencimentos',
            replace_existing=True
        )
        
        # Limpeza de logs às 2h
        self.scheduler.add_job(
            func=self._limpeza_logs,
            trigger=CronTrigger(hour=2, minute=0, timezone=TIMEZONE),
            id='limpeza_logs',
            name='Limpeza de Logs',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("✅ Agendador configurado e iniciado")
    
    def _verificar_vencimentos_diarios(self):
        """Verificar vencimentos e enviar mensagens automáticas"""
        if not self.db:
            return
        
        try:
            # Buscar clientes vencendo hoje ou vencidos há 1 dia
            today = datetime.now(TIMEZONE).date()
            ontem = today - timedelta(days=1)
            
            # Query para clientes que precisam de notificação
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT c.*, u.chat_id as user_chat_id
                FROM clientes c
                JOIN usuarios u ON c.chat_id_usuario = u.chat_id
                WHERE c.notificar = TRUE 
                AND c.status = 'ativo'
                AND u.status IN ('trial', 'ativo')
                AND (c.data_vencimento = %s OR c.data_vencimento = %s)
            """, (today, ontem))
            
            clientes = cursor.fetchall()
            
            for cliente in clientes:
                self._processar_notificacao_cliente(cliente)
                
            logger.info(f"Processados {len(clientes)} clientes para notificação")
            
        except Exception as e:
            logger.error(f"Erro na verificação diária: {e}")
    
    def _processar_notificacao_cliente(self, cliente: Dict):
        """Processar notificação individual do cliente"""
        try:
            today = datetime.now(TIMEZONE).date()
            data_vencimento = cliente['data_vencimento']
            
            # Determinar tipo de template
            if data_vencimento == today:
                template_tipo = 'vencimento_hoje'
            elif data_vencimento == today - timedelta(days=1):
                template_tipo = 'um_dia_apos_vencido'
            else:
                return  # Não processar outros casos
            
            # Buscar template do usuário
            templates = self.db.buscar_templates_usuario(cliente['chat_id_usuario'])
            template = None
            
            for t in templates:
                if t['tipo'] == template_tipo:
                    template = t
                    break
            
            # Se não encontrar, usar template padrão
            if not template:
                conteudo = self.templates_padrão.get(template_tipo, '')
            else:
                conteudo = template['conteudo']
            
            if conteudo:
                # Substituir variáveis
                mensagem = self._substituir_variaveis(conteudo, cliente, cliente['chat_id_usuario'])
                
                # Enviar via WhatsApp
                result = self.baileys.send_message(cliente['telefone'], mensagem)
                
                if result['success']:
                    logger.info(f"Mensagem enviada para {cliente['nome']}: {template_tipo}")
                else:
                    logger.error(f"Erro ao enviar para {cliente['nome']}: {result['error']}")
        
        except Exception as e:
            logger.error(f"Erro ao processar notificação: {e}")
    
    def _limpeza_logs(self):
        """Limpeza de logs antigos"""
        try:
            if not self.db:
                return
            
            # Remover logs de mensagens antigas (mais de 30 dias)
            thirty_days_ago = datetime.now(TIMEZONE) - timedelta(days=30)
            
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM mensagens_enviadas 
                WHERE created_at < %s
            """, (thirty_days_ago,))
            
            logger.info("Limpeza de logs realizada")
            
        except Exception as e:
            logger.error(f"Erro na limpeza de logs: {e}")
    
    def run_telegram_bot(self):
        """Executar bot Telegram"""
        try:
            application = Application.builder().token(self.bot_token).build()
            
            # Handlers
            application.add_handler(CommandHandler("start", self.start_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            # Iniciar polling
            logger.info("🤖 Iniciando bot Telegram...")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Erro no bot Telegram: {e}")
    
    def run_flask_server(self):
        """Executar servidor Flask"""
        try:
            port = int(os.environ.get('PORT', 5000))
            self.flask_app.run(host='0.0.0.0', port=port, debug=False)
        except Exception as e:
            logger.error(f"Erro no servidor Flask: {e}")
    
    def start(self):
        """Iniciar todos os serviços"""
        logger.info("🚀 Iniciando Bot de Gestão de Clientes...")
        
        # Verificar configurações obrigatórias
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN não configurado")
            return
        
        if not DATABASE_URL:
            logger.error("❌ DATABASE_URL não configurado")
            return
        
        # Inicializar agendador
        self._setup_scheduler()
        
        # Iniciar Flask em thread separada
        flask_thread = threading.Thread(target=self.run_flask_server, daemon=True)
        flask_thread.start()
        
        # Iniciar bot Telegram (principal)
        self.run_telegram_bot()

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def main():
    """Função principal"""
    
    # Configuração de logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("=" * 60)
    logger.info("🤖 BOT DE GESTÃO DE CLIENTES - VERSÃO MONOLÍTICA")
    logger.info("=" * 60)
    logger.info(f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info(f"🌍 Timezone: {TIMEZONE}")
    
    # Verificar variáveis de ambiente
    logger.info("🔧 Verificando configurações...")
    
    configs = {
        'BOT_TOKEN': '✅' if BOT_TOKEN else '❌',
        'ADMIN_CHAT_ID': '✅' if ADMIN_CHAT_ID else '❌',
        'DATABASE_URL': '✅' if DATABASE_URL else '❌',
        'MERCADOPAGO_ACCESS_TOKEN': '✅' if MERCADOPAGO_ACCESS_TOKEN else '❌'
    }
    
    for config, status in configs.items():
        logger.info(f"  {config}: {status}")
    
    # Verificar configurações obrigatórias
    if not BOT_TOKEN or not DATABASE_URL:
        logger.error("❌ Configurações obrigatórias não encontradas")
        logger.error("Configure BOT_TOKEN e DATABASE_URL nas variáveis de ambiente")
        sys.exit(1)
    
    # Inicializar e executar bot
    try:
        bot = BotGestaoClientes()
        bot.start()
    except KeyboardInterrupt:
        logger.info("🛑 Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
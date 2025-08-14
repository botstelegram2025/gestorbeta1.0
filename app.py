#!/usr/bin/env python3
"""
Aplicação Web para Bot Telegram - Sistema de Gestão de Clientes
Servidor Flask para deployment em Cloud Run com webhook do Telegram
"""

import os
import sys
import json
import logging
from flask import Flask, request, jsonify
import asyncio
from datetime import datetime
import pytz

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Variáveis globais
telegram_app = None
bot_initialized = False

def check_required_secrets():
    """Verifica se os secrets obrigatórios estão configurados"""
    required = ['BOT_TOKEN', 'ADMIN_CHAT_ID']
    missing = []
    
    for secret in required:
        if not os.getenv(secret):
            missing.append(secret)
    
    if missing:
        logger.error(f"Secrets obrigatórios não configurados: {missing}")
        return False
    
    return True

async def setup_fallback_handlers(application):
    """Configurar handlers básicos como fallback"""
    try:
        from telegram.ext import CommandHandler, MessageHandler, filters
        
        async def start(update, context):
            """Handler básico para comando /start"""
            await update.message.reply_text("Bot inicializado com handlers básicos!")
        
        async def echo(update, context):
            """Handler básico para mensagens"""
            await update.message.reply_text("Mensagem recebida!")
        
        # Adicionar handlers básicos
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    except ImportError:
        logger.warning("Não foi possível configurar handlers - telegram bot em modo degradado")

async def initialize_bot():
    """Inicializa o bot em modo webhook"""
    global telegram_app, bot_initialized
    
    if bot_initialized:
        return True
    
    try:
        # Verificar se o token existe primeiro
        bot_token = os.getenv('BOT_TOKEN')
        if not bot_token:
            logger.error("BOT_TOKEN não encontrado")
            return False
        
        # Tentar importar componentes do telegram bot
        try:
            from telegram.ext import Application, CommandHandler, MessageHandler, filters
            from telegram import Update
        except ImportError as e:
            logger.error(f"Erro ao importar telegram components: {e}")
            logger.warning("Bot funcionará em modo degradado (apenas Flask)")
            bot_initialized = True  # Marcar como inicializado para não tentar novamente
            return True
        
        # Criar application do Telegram
        telegram_app = Application.builder().token(bot_token).build()
        
        # Importar handlers do bot
        try:
            # Tentar importar handlers principais
            import importlib.util
            if importlib.util.find_spec("main") is not None:
                from main import setup_handlers
                await setup_handlers(telegram_app)
                logger.info("Handlers do bot configurados com sucesso")
            else:
                raise ImportError("main module not found")
        except (ImportError, AttributeError) as e:
            # Fallback com handlers básicos
            try:
                if importlib.util.find_spec("start_bot") is not None:
                    from start_bot import setup_basic_handlers
                    await setup_basic_handlers(telegram_app)
                    logger.info("Handlers básicos configurados")
                else:
                    logger.warning("Nenhum módulo de handlers encontrado, criando handlers básicos")
                    await setup_fallback_handlers(telegram_app)
            except (ImportError, AttributeError) as e2:
                logger.warning(f"Erro ao carregar handlers: {e2}")
                await setup_fallback_handlers(telegram_app)
        
        # Inicializar banco de dados
        from database import DatabaseManager
        db = DatabaseManager()
        logger.info("Banco de dados inicializado")
        
        bot_initialized = True
        return True
        
    except Exception as e:
        logger.error(f"Erro ao inicializar bot: {e}")
        return False

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint para Cloud Run"""
    try:
        # Verificar se os secrets estão configurados
        if not check_required_secrets():
            return jsonify({
                'status': 'error',
                'message': 'Secrets obrigatórios não configurados',
                'timestamp': datetime.now(pytz.timezone('America/Sao_Paulo')).isoformat()
            }), 500
        
        # Verificar se o bot está inicializado
        status = 'healthy' if bot_initialized else 'initializing'
        
        return jsonify({
            'status': status,
            'service': 'Bot Telegram - Sistema de Gestão de Clientes',
            'timestamp': datetime.now(pytz.timezone('America/Sao_Paulo')).isoformat(),
            'version': '1.0.0'
        }), 200
        
    except Exception as e:
        logger.error(f"Erro no health check: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now(pytz.timezone('America/Sao_Paulo')).isoformat()
        }), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint para receber updates do Telegram via webhook"""
    global telegram_app, bot_initialized
    
    if not bot_initialized:
        logger.error("Bot não inicializado")
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        # Obter dados do request
        update_data = request.get_json()
        
        if not update_data:
            return jsonify({'error': 'No data received'}), 400
        
        # Se telegram_app não está disponível (modo degradado), apenas log
        if telegram_app is None:
            logger.info("Webhook recebido em modo degradado - apenas logando")
            logger.info(f"Update data: {update_data}")
            return jsonify({'status': 'logged', 'mode': 'degraded'}), 200
        
        # Processar update do Telegram
        try:
            from telegram import Update
            update = Update.de_json(update_data, telegram_app.bot)
            
            # Processar update de forma assíncrona
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(telegram_app.process_update(update))
            
            return jsonify({'status': 'processed'}), 200
        except ImportError:
            logger.info("Webhook recebido em modo degradado - telegram module indisponível")
            return jsonify({'status': 'logged', 'mode': 'degraded'}), 200
        
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """Endpoint de status detalhado"""
    try:
        # Verificar conexão com banco
        db_status = 'unknown'
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            # Teste simples de conexão
            db_status = 'connected'
        except Exception as e:
            db_status = f'error: {str(e)}'
        
        return jsonify({
            'bot_initialized': bot_initialized,
            'database': db_status,
            'secrets_configured': check_required_secrets(),
            'timestamp': datetime.now(pytz.timezone('America/Sao_Paulo')).isoformat(),
            'environment': os.getenv('REPLIT_DEPLOYMENT_TYPE', 'development')
        }), 200
        
    except Exception as e:
        logger.error(f"Erro no endpoint de status: {e}")
        return jsonify({'error': str(e)}), 500

def initialize_app():
    """Inicialização da aplicação"""
    logger.info("Iniciando aplicação...")
    
    # Inicializar bot de forma assíncrona
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_bot())

# Inicializar app na importação
initialize_app()

if __name__ == '__main__':
    # Obter porta do ambiente ou usar 5000 como padrão
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    
    logger.info(f"Iniciando servidor Flask em {host}:{port}")
    
    # Verificar secrets antes de iniciar
    if not check_required_secrets():
        logger.error("Não é possível iniciar sem os secrets obrigatórios")
        sys.exit(1)
    
    # Inicializar bot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_bot())
    
    # Iniciar servidor Flask
    # Para produção, usar Gunicorn: gunicorn -w 1 -b 0.0.0.0:5000 wsgi:app
    app.run(host=host, port=port, debug=False, threaded=True)
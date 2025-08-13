#!/usr/bin/env python3
"""
API para backup e restauração de sessões WhatsApp
Salva dados da sessão no PostgreSQL para persistência entre deploys
"""

import json
import logging
import psycopg2.extras
from flask import Blueprint, request, jsonify
from database import DatabaseManager
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Blueprint para as APIs de sessão
session_api = Blueprint('session_api', __name__)

class WhatsAppSessionManager:
    def __init__(self, db_manager):
        self.db = db_manager
        self._create_session_table()
    
    def _create_session_table(self):
        """Cria tabela para armazenar sessões WhatsApp"""
        try:
            query = """
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(100) DEFAULT 'default' UNIQUE,
                session_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    conn.commit()
            logger.info("✅ Tabela whatsapp_sessions criada/verificada")
            
        except Exception as e:
            logger.error(f"Erro ao criar tabela de sessões: {e}")
    
    def backup_session(self, session_data, session_id='default'):
        """Salva dados da sessão no banco"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Verificar se já existe
                    check_query = "SELECT id FROM whatsapp_sessions WHERE session_id = %s"
                    cursor.execute(check_query, (session_id,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Atualizar existente
                        update_query = """
                        UPDATE whatsapp_sessions 
                        SET session_data = %s, updated_at = CURRENT_TIMESTAMP 
                        WHERE session_id = %s
                        """
                        cursor.execute(update_query, (json.dumps(session_data), session_id))
                        logger.info(f"✅ Sessão {session_id} atualizada no banco")
                    else:
                        # Inserir nova
                        insert_query = """
                        INSERT INTO whatsapp_sessions (session_id, session_data) 
                        VALUES (%s, %s)
                        """
                        cursor.execute(insert_query, (session_id, json.dumps(session_data)))
                        logger.info(f"✅ Nova sessão {session_id} salva no banco")
                    
                    conn.commit()
                    return True
            
        except Exception as e:
            logger.error(f"Erro ao salvar sessão: {e}")
            return False
    
    def restore_session(self, session_id='default'):
        """Restaura dados da sessão do banco"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    query = """
                    SELECT session_data FROM whatsapp_sessions 
                    WHERE session_id = %s 
                    ORDER BY updated_at DESC LIMIT 1
                    """
                    cursor.execute(query, (session_id,))
                    result = cursor.fetchone()
                    
                    if result:
                        session_data = result['session_data']
                        logger.info(f"✅ Sessão {session_id} restaurada do banco")
                        return session_data
                    else:
                        logger.info(f"ℹ️ Nenhuma sessão {session_id} encontrada no banco")
                        return None
                        
        except Exception as e:
            logger.error(f"Erro ao restaurar sessão: {e}")
            return None
    
    def delete_session(self, session_id='default'):
        """Remove sessão do banco"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = "DELETE FROM whatsapp_sessions WHERE session_id = %s"
                    cursor.execute(query, (session_id,))
                    conn.commit()
            logger.info(f"✅ Sessão {session_id} removida do banco")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao remover sessão: {e}")
            return False

# Instância global do gerenciador
session_manager = None

def init_session_manager(db_manager):
    """Inicializa o gerenciador de sessões"""
    global session_manager
    session_manager = WhatsAppSessionManager(db_manager)
    logger.info("✅ WhatsApp Session Manager inicializado")

@session_api.route('/api/session/backup', methods=['POST'])
def backup_session():
    """Endpoint para backup da sessão"""
    try:
        if not session_manager:
            return jsonify({'success': False, 'error': 'Session manager não inicializado'}), 500
        
        data = request.get_json()
        if not data or 'session_data' not in data:
            return jsonify({'success': False, 'error': 'session_data é obrigatório'}), 400
        
        session_data = data['session_data']
        session_id = data.get('session_id', 'default')
        
        success = session_manager.backup_session(session_data, session_id)
        
        if success:
            return jsonify({
                'success': True, 
                'message': f'Sessão {session_id} salva com sucesso',
                'files_count': len(session_data) if isinstance(session_data, dict) else 0
            })
        else:
            return jsonify({'success': False, 'error': 'Erro ao salvar sessão'}), 500
            
    except Exception as e:
        logger.error(f"Erro no backup da sessão: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@session_api.route('/api/session/restore', methods=['GET'])
def restore_session():
    """Endpoint para restaurar sessão"""
    try:
        if not session_manager:
            return jsonify({'success': False, 'error': 'Session manager não inicializado'}), 500
        
        session_id = request.args.get('session_id', 'default')
        session_data = session_manager.restore_session(session_id)
        
        if session_data:
            return jsonify({
                'success': True, 
                'session_data': session_data,
                'files_count': len(session_data) if isinstance(session_data, dict) else 0
            })
        else:
            return jsonify({
                'success': False, 
                'session_data': {},
                'message': 'Nenhuma sessão encontrada'
            })
            
    except Exception as e:
        logger.error(f"Erro ao restaurar sessão: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@session_api.route('/api/session/delete', methods=['DELETE'])
def delete_session():
    """Endpoint para deletar sessão"""
    try:
        if not session_manager:
            return jsonify({'success': False, 'error': 'Session manager não inicializado'}), 500
        
        session_id = request.args.get('session_id', 'default')
        success = session_manager.delete_session(session_id)
        
        if success:
            return jsonify({
                'success': True, 
                'message': f'Sessão {session_id} removida com sucesso'
            })
        else:
            return jsonify({'success': False, 'error': 'Erro ao remover sessão'}), 500
            
    except Exception as e:
        logger.error(f"Erro ao deletar sessão: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@session_api.route('/api/session/status', methods=['GET'])
def session_status():
    """Status das sessões armazenadas"""
    try:
        if not session_manager:
            return jsonify({'success': False, 'error': 'Session manager não inicializado'}), 500
        
        with session_manager.db.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                query = """
                SELECT session_id, 
                       EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - updated_at)) as seconds_ago,
                       updated_at
                FROM whatsapp_sessions 
                ORDER BY updated_at DESC
                """
                cursor.execute(query)
                results = cursor.fetchall()
        
        sessions = []
        for row in results:
            sessions.append({
                'session_id': row['session_id'],
                'last_updated': row['updated_at'].isoformat() if row['updated_at'] else None,
                'seconds_ago': int(row['seconds_ago']) if row['seconds_ago'] else None
            })
        
        return jsonify({
            'success': True,
            'sessions_count': len(sessions),
            'sessions': sessions
        })
        
    except Exception as e:
        logger.error(f"Erro ao obter status das sessões: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
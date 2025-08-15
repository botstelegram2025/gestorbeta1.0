#!/usr/bin/env python3
"""
Correção crítica: Isolamento WhatsApp por usuário
Cada usuário deve ter sua própria sessão WhatsApp
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_whatsapp_sessions():
    """Corrigir sistema de sessões WhatsApp para isolamento por usuário"""
    
    database_url = os.getenv('DATABASE_URL')
    conn = psycopg2.connect(database_url)
    conn.set_session(autocommit=True)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    logger.info("🔧 Corrigindo sessões WhatsApp...")
    
    # 1. Adicionar campo user_id se não existir
    cursor.execute("""
        ALTER TABLE whatsapp_sessions 
        ADD COLUMN IF NOT EXISTS user_id BIGINT;
    """)
    
    # 2. Atualizar sessões existentes para o admin
    cursor.execute("""
        UPDATE whatsapp_sessions 
        SET user_id = 1460561545 
        WHERE user_id IS NULL;
    """)
    
    # 3. Modificar session_id para incluir user_id
    cursor.execute("""
        UPDATE whatsapp_sessions 
        SET session_id = CONCAT('user_', user_id::text, '_', session_id)
        WHERE session_id NOT LIKE 'user_%';
    """)
    
    # 4. Criar constraint unique por usuário
    cursor.execute("DROP INDEX IF EXISTS whatsapp_sessions_session_id_key")
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_sessions_user_session_unique 
        ON whatsapp_sessions(user_id, session_id);
    """)
    
    logger.info("✅ Sessões WhatsApp isoladas por usuário!")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    fix_whatsapp_sessions()
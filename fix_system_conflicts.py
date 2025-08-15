#!/usr/bin/env python3
"""
Script para corrigir conflitos críticos do sistema
- Separar dados admin/usuários
- Corrigir isolamento WhatsApp por usuário
- Consertar templates duplicados
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_connection():
    """Conectar ao banco"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL não configurada")
    
    conn = psycopg2.connect(database_url)
    conn.set_session(autocommit=True)
    return conn

def fix_user_isolation():
    """Corrigir isolamento entre usuários"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    logger.info("🔧 Corrigindo isolamento de usuários...")
    
    # 1. Verificar e corrigir estrutura das tabelas
    logger.info("📋 Verificando estrutura das tabelas...")
    
    # Adicionar chat_id_usuario em templates se não existir
    cursor.execute("""
        ALTER TABLE templates 
        ADD COLUMN IF NOT EXISTS chat_id_usuario BIGINT;
    """)
    
    # Adicionar chat_id_usuario em configuracoes se não existir  
    cursor.execute("""
        ALTER TABLE configuracoes 
        ADD COLUMN IF NOT EXISTS chat_id_usuario BIGINT;
    """)
    
    # 2. Migrar templates globais para admin
    logger.info("📄 Migrando templates globais para admin...")
    cursor.execute("""
        UPDATE templates 
        SET chat_id_usuario = 1460561545 
        WHERE chat_id_usuario IS NULL;
    """)
    
    # 3. Migrar configuracoes globais para admin
    logger.info("⚙️ Migrando configurações globais para admin...")
    cursor.execute("""
        UPDATE configuracoes 
        SET chat_id_usuario = 1460561545 
        WHERE chat_id_usuario IS NULL;
    """)
    
    # 4. Verificar usuários problemáticos
    cursor.execute("SELECT chat_id, nome FROM usuarios WHERE nome LIKE '/%' OR nome = ''")
    usuarios_problematicos = cursor.fetchall()
    
    for usuario in usuarios_problematicos:
        logger.warning(f"⚠️ Usuário problemático: {usuario['chat_id']} - {usuario['nome']}")
        
        # Limpar dados relacionados
        cursor.execute("DELETE FROM templates WHERE chat_id_usuario = %s", (usuario['chat_id'],))
        cursor.execute("DELETE FROM configuracoes WHERE chat_id_usuario = %s", (usuario['chat_id'],))
        cursor.execute("DELETE FROM clientes WHERE chat_id_usuario = %s", (usuario['chat_id'],))
        cursor.execute("DELETE FROM usuarios WHERE chat_id = %s", (usuario['chat_id'],))
        
        logger.info(f"✅ Usuário {usuario['chat_id']} removido")
    
    cursor.close()
    conn.close()
    
    logger.info("✅ Isolamento de usuários corrigido!")

def fix_whatsapp_isolation():
    """Corrigir isolamento do WhatsApp por usuário"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    logger.info("📱 Corrigindo isolamento WhatsApp...")
    
    # Adicionar campo user_id em whatsapp_sessions se não existir
    cursor.execute("""
        ALTER TABLE whatsapp_sessions 
        ADD COLUMN IF NOT EXISTS user_id BIGINT DEFAULT NULL;
    """)
    
    # Marcar sessões existentes como do admin
    cursor.execute("""
        UPDATE whatsapp_sessions 
        SET user_id = 1460561545 
        WHERE user_id IS NULL;
    """)
    
    # Criar índice para performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_sessions_user_id 
        ON whatsapp_sessions(user_id);
    """)
    
    cursor.close()
    conn.close()
    
    logger.info("✅ Isolamento WhatsApp corrigido!")

def fix_template_system():
    """Corrigir sistema de templates para isolamento por usuário"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    logger.info("📝 Corrigindo sistema de templates...")
    
    # Verificar templates duplicados
    cursor.execute("""
        SELECT nome, COUNT(*) as total, array_agg(chat_id_usuario) as usuarios
        FROM templates 
        GROUP BY nome 
        HAVING COUNT(*) > 1;
    """)
    
    duplicados = cursor.fetchall()
    
    for dup in duplicados:
        logger.warning(f"⚠️ Template duplicado: {dup['nome']} - Usuários: {dup['usuarios']}")
        
        # Manter apenas do admin, remover dos outros usuários
        cursor.execute("""
            DELETE FROM templates 
            WHERE nome = %s AND chat_id_usuario != 1460561545
        """, (dup['nome'],))
        
        logger.info(f"✅ Duplicados removidos para: {dup['nome']}")
    
    # Atualizar constraint para permitir templates únicos por usuário
    cursor.execute("DROP INDEX IF EXISTS templates_nome_key")
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS templates_nome_usuario_unique 
        ON templates(nome, chat_id_usuario);
    """)
    
    cursor.close()
    conn.close()
    
    logger.info("✅ Sistema de templates corrigido!")

def fix_client_data():
    """Corrigir dados de clientes"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    logger.info("👥 Verificando dados de clientes...")
    
    # Verificar clientes sem usuário válido
    cursor.execute("""
        SELECT c.id, c.nome, c.chat_id_usuario, u.nome as usuario_nome
        FROM clientes c
        LEFT JOIN usuarios u ON c.chat_id_usuario = u.chat_id
        WHERE u.chat_id IS NULL;
    """)
    
    clientes_orfaos = cursor.fetchall()
    
    if clientes_orfaos:
        logger.warning(f"⚠️ {len(clientes_orfaos)} clientes órfãos encontrados")
        for cliente in clientes_orfaos:
            logger.warning(f"  - Cliente {cliente['id']}: {cliente['nome']} (usuário: {cliente['chat_id_usuario']})")
            
            # Mover para admin temporariamente
            cursor.execute("""
                UPDATE clientes 
                SET chat_id_usuario = 1460561545 
                WHERE id = %s
            """, (cliente['id'],))
        
        logger.info("✅ Clientes órfãos movidos para admin")
    
    cursor.close()
    conn.close()
    
    logger.info("✅ Dados de clientes verificados!")

def generate_status_report():
    """Gerar relatório de status do sistema"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    logger.info("📊 Gerando relatório de status...")
    
    # Contar registros por tabela
    tabelas = ['usuarios', 'clientes', 'templates', 'configuracoes', 'whatsapp_sessions']
    
    for tabela in tabelas:
        cursor.execute(f"SELECT COUNT(*) as total FROM {tabela}")
        total = cursor.fetchone()['total']
        logger.info(f"  {tabela}: {total} registros")
    
    # Usuários ativos
    cursor.execute("SELECT chat_id, nome, status FROM usuarios ORDER BY data_cadastro")
    usuarios = cursor.fetchall()
    
    logger.info("\n👥 Usuários no sistema:")
    for user in usuarios:
        logger.info(f"  - {user['chat_id']}: {user['nome']} ({user['status']})")
    
    # Templates por usuário
    cursor.execute("""
        SELECT chat_id_usuario, COUNT(*) as total_templates
        FROM templates 
        GROUP BY chat_id_usuario 
        ORDER BY chat_id_usuario
    """)
    templates_por_usuario = cursor.fetchall()
    
    logger.info("\n📝 Templates por usuário:")
    for item in templates_por_usuario:
        cursor.execute("SELECT nome FROM usuarios WHERE chat_id = %s", (item['chat_id_usuario'],))
        usuario = cursor.fetchone()
        nome_usuario = usuario['nome'] if usuario else 'Usuário não encontrado'
        logger.info(f"  - {item['chat_id_usuario']} ({nome_usuario}): {item['total_templates']} templates")
    
    # Clientes por usuário
    cursor.execute("""
        SELECT chat_id_usuario, COUNT(*) as total_clientes
        FROM clientes 
        GROUP BY chat_id_usuario 
        ORDER BY chat_id_usuario
    """)
    clientes_por_usuario = cursor.fetchall()
    
    logger.info("\n👥 Clientes por usuário:")
    for item in clientes_por_usuario:
        cursor.execute("SELECT nome FROM usuarios WHERE chat_id = %s", (item['chat_id_usuario'],))
        usuario = cursor.fetchone()
        nome_usuario = usuario['nome'] if usuario else 'Usuário não encontrado'
        logger.info(f"  - {item['chat_id_usuario']} ({nome_usuario}): {item['total_clientes']} clientes")
    
    cursor.close()
    conn.close()
    
    logger.info("✅ Relatório de status concluído!")

def main():
    """Executar todas as correções"""
    logger.info("🚀 Iniciando correções do sistema...")
    
    try:
        # 1. Corrigir isolamento de usuários
        fix_user_isolation()
        
        # 2. Corrigir isolamento WhatsApp
        fix_whatsapp_isolation()
        
        # 3. Corrigir sistema de templates
        fix_template_system()
        
        # 4. Corrigir dados de clientes
        fix_client_data()
        
        # 5. Gerar relatório
        generate_status_report()
        
        logger.info("🎉 Todas as correções concluídas com sucesso!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro durante correções: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
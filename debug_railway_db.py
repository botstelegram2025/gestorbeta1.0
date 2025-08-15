#!/usr/bin/env python3
"""
Script para debug do banco PostgreSQL no Railway
Testa conectividade, criação de tabelas e inserção de dados
"""
import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import time

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_railway_database():
    """Testar conexão e operações no banco Railway"""
    
    # Configurações do banco
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        logger.error("❌ DATABASE_URL não encontrada!")
        return False
    
    logger.info(f"🔧 DATABASE_URL encontrada: {database_url[:50]}...")
    
    try:
        # Tentar conexão
        logger.info("🔄 Tentando conectar ao PostgreSQL...")
        conn = psycopg2.connect(database_url)
        conn.set_session(autocommit=True)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        logger.info("✅ Conectado com sucesso!")
        
        # Verificar tabelas existentes
        logger.info("📋 Verificando tabelas existentes...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        tabelas = cursor.fetchall()
        if tabelas:
            logger.info(f"📊 Tabelas encontradas ({len(tabelas)}):")
            for tabela in tabelas:
                logger.info(f"  - {tabela['table_name']}")
        else:
            logger.warning("⚠️ Nenhuma tabela encontrada!")
        
        # Testar criação de tabela de teste
        logger.info("🧪 Testando criação de tabela...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teste_railway (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(100),
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("✅ Tabela de teste criada!")
        
        # Testar inserção
        logger.info("📝 Testando inserção...")
        cursor.execute("""
            INSERT INTO teste_railway (nome) VALUES (%s)
        """, ("Teste Railway Deploy",))
        logger.info("✅ Dados inseridos!")
        
        # Verificar dados
        cursor.execute("SELECT * FROM teste_railway ORDER BY id DESC LIMIT 1")
        resultado = cursor.fetchone()
        if resultado:
            logger.info(f"✅ Dados recuperados: {dict(resultado)}")
        
        # Limpar tabela de teste
        cursor.execute("DROP TABLE IF EXISTS teste_railway")
        logger.info("🧹 Tabela de teste removida")
        
        cursor.close()
        conn.close()
        
        logger.info("🎉 Teste completo - Banco funcionando perfeitamente!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro no teste do banco: {e}")
        logger.error(f"Tipo do erro: {type(e).__name__}")
        return False

def test_table_creation():
    """Testar especificamente criação das tabelas do sistema"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        logger.error("❌ DATABASE_URL não encontrada!")
        return False
    
    try:
        conn = psycopg2.connect(database_url)
        conn.set_session(autocommit=True)
        cursor = conn.cursor()
        
        logger.info("🏗️ Testando criação das tabelas do sistema...")
        
        # Tabela clientes
        logger.info("📋 Criando tabela clientes...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                telefone VARCHAR(20) UNIQUE NOT NULL,
                vencimento DATE NOT NULL,
                valor DECIMAL(10,2) NOT NULL,
                plano VARCHAR(100) NOT NULL,
                status VARCHAR(20) DEFAULT 'ativo',
                usuario_id INTEGER,
                receber_cobranca BOOLEAN DEFAULT TRUE,
                receber_notificacoes BOOLEAN DEFAULT TRUE,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("✅ Tabela clientes criada!")
        
        # Tabela templates
        logger.info("📄 Criando tabela templates...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                tipo VARCHAR(50) NOT NULL,
                conteudo TEXT NOT NULL,
                ativo BOOLEAN DEFAULT TRUE,
                uso_count INTEGER DEFAULT 0,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("✅ Tabela templates criada!")
        
        # Verificar se tabelas foram criadas
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('clientes', 'templates')
        """)
        
        tabelas_criadas = cursor.fetchall()
        logger.info(f"✅ Tabelas do sistema criadas: {[t[0] for t in tabelas_criadas]}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar tabelas: {e}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Iniciando debug do banco Railway...")
    
    # Aguardar um pouco (Railway pode estar inicializando)
    time.sleep(5)
    
    success = test_railway_database()
    
    if success:
        logger.info("🎯 Testando criação específica das tabelas...")
        test_table_creation()
    
    sys.exit(0 if success else 1)
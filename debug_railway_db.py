#!/usr/bin/env python3
"""
Script de debug para testar conectividade do PostgreSQL no Railway
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_database_connection():
    """Testa diferentes formas de conectar ao PostgreSQL"""
    
    # Método 1: Usando DATABASE_URL diretamente
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        logger.info(f"DATABASE_URL encontrada: {database_url[:50]}...")
        try:
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()
                logger.info(f"✅ Conexão DATABASE_URL OK: {version[0]}")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Erro com DATABASE_URL: {e}")
    
    # Método 2: Usando variáveis individuais
    connection_params = {
        'host': os.getenv('PGHOST', 'localhost'),
        'database': os.getenv('PGDATABASE', 'bot_clientes'),
        'user': os.getenv('PGUSER', 'postgres'),
        'password': os.getenv('PGPASSWORD', ''),
        'port': os.getenv('PGPORT', '5432')
    }
    
    logger.info(f"Tentando conexão com parâmetros individuais:")
    logger.info(f"- Host: {connection_params['host']}")
    logger.info(f"- Database: {connection_params['database']}")
    logger.info(f"- User: {connection_params['user']}")
    logger.info(f"- Port: {connection_params['port']}")
    
    try:
        conn = psycopg2.connect(**connection_params)
        with conn.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            db_info = cursor.fetchone()
            logger.info(f"✅ Conexão parâmetros OK: DB={db_info[0]}, USER={db_info[1]}")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Erro com parâmetros individuais: {e}")
    
    return False

def test_table_creation():
    """Testa criação de tabela simples"""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL não encontrada")
            return False
            
        conn = psycopg2.connect(database_url)
        with conn.cursor() as cursor:
            # Criar tabela de teste
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_railway (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Inserir dado de teste
            cursor.execute("INSERT INTO test_railway (name) VALUES (%s)", ("teste_railway",))
            
            # Ler dado de teste
            cursor.execute("SELECT * FROM test_railway WHERE name = %s", ("teste_railway",))
            result = cursor.fetchone()
            
            logger.info(f"✅ Teste de tabela OK: {result}")
            
            # Limpar tabela de teste
            cursor.execute("DROP TABLE IF EXISTS test_railway")
            
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro no teste de tabela: {e}")
        return False

if __name__ == "__main__":
    logger.info("🔍 Iniciando testes de conectividade Railway PostgreSQL...")
    
    logger.info("\n=== Teste 1: Conectividade ===")
    connection_ok = test_database_connection()
    
    if connection_ok:
        logger.info("\n=== Teste 2: Criação de Tabela ===")
        table_ok = test_table_creation()
        
        if table_ok:
            logger.info("\n✅ Todos os testes passaram! O banco está funcionando.")
        else:
            logger.error("\n❌ Problema na criação de tabelas.")
    else:
        logger.error("\n❌ Problema de conectividade básica.")
    
    logger.info("\nVerifique as variáveis de ambiente no Railway:")
    for var in ['DATABASE_URL', 'PGHOST', 'PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGPORT']:
        value = os.getenv(var)
        if value:
            if 'PASSWORD' in var:
                logger.info(f"- {var}: ****** (oculta)")
            else:
                logger.info(f"- {var}: {value}")
        else:
            logger.info(f"- {var}: ❌ NÃO DEFINIDA")
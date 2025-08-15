#!/usr/bin/env python3
"""
Versão corrigida do database.py para Railway
Inclui retry robusto e configuração otimizada
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import time
from urllib.parse import urlparse

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.connection_params = self._get_connection_params()
        logger.info("🔧 DatabaseManager inicializado para Railway")
    
    def _get_connection_params(self):
        """Obter parâmetros de conexão otimizados para Railway"""
        database_url = os.getenv('DATABASE_URL')
        
        if not database_url:
            logger.error("❌ DATABASE_URL não configurada!")
            raise ValueError("DATABASE_URL é obrigatória")
        
        # Parse da URL
        parsed = urlparse(database_url)
        
        params = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path.lstrip('/'),
            'user': parsed.username,
            'password': parsed.password,
            # Configurações otimizadas para Railway
            'connect_timeout': 30,
            'command_timeout': 60,
            'application_name': 'railway_bot',
            'sslmode': 'require' if 'railway' in parsed.hostname else 'prefer'
        }
        
        logger.info(f"🔧 Configuração do banco:")
        logger.info(f"- Host: {params['host']}")
        logger.info(f"- Database: {params['database']}")
        logger.info(f"- User: {params['user']}")
        logger.info(f"- Port: {params['port']}")
        
        return params
    
    def get_connection(self):
        """Obter conexão com retry automático"""
        max_attempts = 5
        retry_delay = 2
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Tentativa {attempt + 1} de conectar ao banco...")
                
                conn = psycopg2.connect(**self.connection_params)
                conn.set_session(autocommit=False)
                
                # Teste básico de conectividade
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                
                logger.info("✅ Conexão estabelecida com sucesso!")
                return conn
                
            except psycopg2.OperationalError as e:
                logger.warning(f"⚠️ Erro de conectividade na tentativa {attempt + 1}: {e}")
                
                if attempt < max_attempts - 1:
                    logger.info(f"🔄 Aguardando {retry_delay}s antes da próxima tentativa...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Backoff exponencial
                else:
                    logger.error("❌ Esgotadas tentativas de conexão!")
                    raise
                    
            except Exception as e:
                logger.error(f"❌ Erro inesperado: {e}")
                raise
    
    def initialize_database(self):
        """Inicializar banco com tratamento robusto de erros"""
        try:
            logger.info("🔄 Inicializando banco de dados...")
            
            conn = self.get_connection()
            
            with conn:
                with conn.cursor() as cursor:
                    # Criar tabelas
                    self.create_tables(cursor)
                    logger.info("✅ Tabelas criadas/verificadas")
                    
                    # Criar índices
                    self.create_indexes(cursor)
                    logger.info("✅ Índices criados/verificados")
                    
                    # Inserir dados padrão
                    self.insert_default_data(cursor)
                    logger.info("✅ Dados padrão inseridos/verificados")
                
                conn.commit()
                logger.info("🎉 Banco de dados inicializado com sucesso!")
                return True
                
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar banco: {e}")
            raise
    
    def create_tables(self, cursor):
        """Criar todas as tabelas necessárias"""
        
        # Tabela de usuários (multi-tenant)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                telefone VARCHAR(20),
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fim_periodo_teste TIMESTAMP,
                ultimo_pagamento TIMESTAMP,
                proximo_vencimento TIMESTAMP,
                status VARCHAR(50) DEFAULT 'teste_gratuito',
                plano_ativo BOOLEAN DEFAULT TRUE,
                total_pagamentos DECIMAL(10, 2) DEFAULT 0,
                dados_adicionais JSONB
            )
        """)
        
        # Tabela de clientes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                chat_id_usuario BIGINT NOT NULL,
                nome VARCHAR(255) NOT NULL,
                telefone VARCHAR(20) NOT NULL,
                pacote VARCHAR(255) NOT NULL,
                valor DECIMAL(10,2) NOT NULL,
                servidor VARCHAR(255),
                vencimento DATE NOT NULL,
                ativo BOOLEAN DEFAULT TRUE,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                info_adicional TEXT,
                receber_cobranca BOOLEAN DEFAULT TRUE,
                receber_notificacoes BOOLEAN DEFAULT TRUE,
                preferencias_notificacao JSONB DEFAULT '{}'
            )
        """)
        
        # Tabela de templates
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) UNIQUE NOT NULL,
                descricao TEXT,
                conteudo TEXT NOT NULL,
                tipo VARCHAR(50) DEFAULT 'geral',
                ativo BOOLEAN DEFAULT TRUE,
                uso_count INTEGER DEFAULT 0,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Outras tabelas...
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                id SERIAL PRIMARY KEY,
                chave VARCHAR(100) UNIQUE NOT NULL,
                valor TEXT,
                descricao TEXT,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs_envio (
                id SERIAL PRIMARY KEY,
                chat_id_usuario BIGINT,
                cliente_id INTEGER REFERENCES clientes(id),
                template_id INTEGER REFERENCES templates(id),
                telefone VARCHAR(20) NOT NULL,
                mensagem TEXT NOT NULL,
                tipo_envio VARCHAR(50) NOT NULL,
                sucesso BOOLEAN NOT NULL,
                erro TEXT,
                message_id VARCHAR(255),
                data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fila_mensagens (
                id SERIAL PRIMARY KEY,
                cliente_id INTEGER REFERENCES clientes(id),
                template_id INTEGER REFERENCES templates(id),
                telefone VARCHAR(20) NOT NULL,
                mensagem TEXT NOT NULL,
                tipo_mensagem VARCHAR(50) NOT NULL,
                agendado_para TIMESTAMP NOT NULL,
                processado BOOLEAN DEFAULT FALSE,
                tentativas INTEGER DEFAULT 0,
                max_tentativas INTEGER DEFAULT 3,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_processamento TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(100) UNIQUE NOT NULL,
                session_data JSONB NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def create_indexes(self, cursor):
        """Criar índices para otimização"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_usuarios_chat_id ON usuarios(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_clientes_usuario ON clientes(chat_id_usuario)",
            "CREATE INDEX IF NOT EXISTS idx_clientes_vencimento ON clientes(vencimento)",
            "CREATE INDEX IF NOT EXISTS idx_logs_usuario ON logs_envio(chat_id_usuario)",
            "CREATE INDEX IF NOT EXISTS idx_fila_agendado ON fila_mensagens(agendado_para)",
            "CREATE INDEX IF NOT EXISTS idx_configuracoes_chave ON configuracoes(chave)"
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except Exception as e:
                logger.warning(f"Aviso ao criar índice: {e}")
    
    def insert_default_data(self, cursor):
        """Inserir dados padrão necessários"""
        
        # Templates padrão
        templates = [
            ('Vencimento Hoje', 'vencimento_hoje', 'Seu plano vence hoje! Renove para manter o acesso.'),
            ('Vencido 1 Dia', 'vencimento_1dia_apos', 'Seu plano venceu ontem. Regularize sua situação.'),
            ('Boas Vindas', 'boas_vindas', 'Bem-vindo! Seu cadastro foi realizado com sucesso.')
        ]
        
        for nome, tipo, conteudo in templates:
            cursor.execute("""
                INSERT INTO templates (nome, tipo, conteudo) 
                VALUES (%s, %s, %s)
                ON CONFLICT (nome) DO NOTHING
            """, (nome, tipo, conteudo))
        
        # Configurações padrão
        configs = [
            ('empresa_nome', 'Minha Empresa', 'Nome da empresa'),
            ('empresa_telefone', '+55 11 99999-9999', 'Telefone de contato'),
            ('horario_envio', '09:00', 'Horário para envio automático'),
            ('timezone', 'America/Sao_Paulo', 'Fuso horário do sistema')
        ]
        
        for chave, valor, descricao in configs:
            cursor.execute("""
                INSERT INTO configuracoes (chave, valor, descricao) 
                VALUES (%s, %s, %s)
                ON CONFLICT (chave) DO NOTHING
            """, (chave, valor, descricao))
    
    def test_connection(self):
        """Testar conectividade do banco"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM usuarios")
                result = cursor.fetchone()
                logger.info(f"✅ Teste de conectividade OK - {result[0]} usuários")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Teste de conectividade falhou: {e}")
            return False

# Instância global
database_manager = DatabaseManager()

def get_db_manager():
    """Obter instância do gerenciador de banco"""
    return database_manager

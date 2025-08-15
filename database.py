"""
Gerenciador de Banco de Dados PostgreSQL
Sistema completo para gestão de clientes, templates e logs
- Compatível com Railway (SSL obrigatório)
- Isolamento multi-tenant por chat_id_usuario (cada usuário vê apenas seus dados)
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime, timedelta
from utils import agora_br, formatar_data_br  # se não usar, pode remover
from models import Cliente, Template, LogEnvio, FilaMensagem  # se não usar, pode remover

logger = logging.getLogger(__name__)

def _mask_conn_dict(d):
    # Não vaze senha nos logs
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if k.lower() in ("password", "pgpassword"):
            out[k] = "****"
        else:
            out[k] = v
    return out


class DatabaseManager:
    def __init__(self):
        """Inicializa conexão com PostgreSQL (compatível Railway/local)"""
        # Tenta usar DATABASE_URL (padrão do Railway)
        self.database_url = os.getenv('DATABASE_URL')

        host = os.getenv('PGHOST', 'localhost')
        # Se não for localhost, exigimos SSL por padrão (Railway)
        default_sslmode = 'disable' if host in ('localhost', '127.0.0.1') else 'require'

        self.connection_params = {
            'host': host,
            'database': os.getenv('PGDATABASE', 'bot_clientes'),
            'user': os.getenv('PGUSER', 'postgres'),
            'password': os.getenv('PGPASSWORD', ''),
            'port': os.getenv('PGPORT', '5432'),
            'sslmode': os.getenv('PGSSLMODE', default_sslmode),
        }

        logger.info("🔧 Configuração do banco:")
        if self.database_url:
            logger.info(f"- DATABASE_URL: {self.database_url[:50]}...")
        logger.info(f"- Parâmetros (sem senha): {_mask_conn_dict(self.connection_params)}")

        # Cache para consultas frequentes
        self._cache = {}
        self._cache_ttl = {}
        self._cache_timeout = 300  # 5 minutos

        self.init_database()

    # -------------------------
    # Helpers
    # -------------------------
    def _require_user(self, chat_id_usuario):
        """Garante que operações multi-tenant recebam o chat_id do usuário."""
        if chat_id_usuario is None:
            raise ValueError("chat_id_usuario é obrigatório para esta operação (isolamento multi-tenant).")
        return chat_id_usuario

    def get_connection(self):
        """Cria nova conexão com o banco - Railway prioritário"""
        # 1) Tenta via DATABASE_URL (força SSL no Railway)
        if self.database_url:
            try:
                # Garante sslmode=require mesmo se a URL não tiver
                conn = psycopg2.connect(self.database_url, sslmode='require')
                conn.autocommit = False
                return conn
            except Exception as e:
                logger.warning(f"Falha com DATABASE_URL: {e}")

        # 2) Fallback para parâmetros individuais
        try:
            conn = psycopg2.connect(**self.connection_params)
            conn.autocommit = False
            return conn
        except Exception as e:
            logger.error(f"Erro ao conectar com PostgreSQL: {e}")
            logger.error(f"DATABASE_URL disponível: {bool(self.database_url)}")
            logger.error(f"Parâmetros (sem senha): {_mask_conn_dict(self.connection_params)}")
            raise

    def _get_cache(self, key):
        """Recupera valor do cache se ainda válido"""
        import time
        if key in self._cache and key in self._cache_ttl:
            if time.time() < self._cache_ttl[key]:
                return self._cache[key]
            else:
                # Cache expirado, remover
                del self._cache[key]
                del self._cache_ttl[key]
        return None

    def _set_cache(self, key, value):
        """Define valor no cache com TTL"""
        import time
        self._cache[key] = value
        self._cache_ttl[key] = time.time() + self._cache_timeout

    # -------------------------
    # Exec helpers
    # -------------------------
    def execute_query(self, query, params=None):
        """Executa uma query de modificação (INSERT, UPDATE, DELETE)"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    conn.commit()
                    return cursor.rowcount
        except Exception as e:
            logger.error(f"Erro ao executar query: {e}")
            raise

    def fetch_one(self, query, params=None):
        """Executa uma query e retorna um único resultado"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Erro ao executar fetch_one: {e}")
            raise

    def fetch_all(self, query, params=None):
        """Executa uma query e retorna todos os resultados"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    results = cursor.fetchall()
                    return [dict(result) for result in results]
        except Exception as e:
            logger.error(f"Erro ao executar fetch_all: {e}")
            raise

    # -------------------------
    # Inicialização
    # -------------------------
    def init_database(self):
        """Inicializa as tabelas do banco de dados com retry para Railway"""
        max_attempts = 5
        retry_delay = 2

        for attempt in range(max_attempts):
            try:
                logger.info(f"Tentativa {attempt + 1} de conectar ao banco...")
                conn = self.get_connection()

                with conn:
                    with conn.cursor() as cursor:
                        # Teste básico
                        cursor.execute("SELECT 1")
                        cursor.fetchone()
                        logger.info("Conectividade básica confirmada")

                        # Estrutura
                        self.create_tables(cursor)
                        self.create_indexes(cursor)
                        self.insert_default_templates(cursor)
                        self.insert_default_configs(cursor)

                    conn.commit()
                    logger.info("Banco de dados inicializado com sucesso!")
                    return True

            except psycopg2.OperationalError as e:
                logger.warning(f"Erro de conectividade na tentativa {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Backoff exponencial
                else:
                    logger.error("Esgotadas tentativas de conexão com PostgreSQL")
                    raise

            except Exception as e:
                logger.error(f"Erro ao inicializar banco de dados: {e}")
                logger.error(f"Detalhes dos parâmetros (sem senha): {_mask_conn_dict(self.connection_params)}")
                raise

        return False

    def create_tables(self, cursor):
        """Cria todas as tabelas necessárias"""

        # Tabela de usuários do sistema (multi-tenant)
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

        # Tabela de pagamentos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                valor DECIMAL(10, 2) NOT NULL,
                data_pagamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                referencia VARCHAR(255),
                status VARCHAR(50) DEFAULT 'pendente',
                payment_id VARCHAR(255),
                dados_pagamento JSONB,
                FOREIGN KEY (chat_id) REFERENCES usuarios(chat_id)
            )
        """)

        # Tabela de clientes (com referência ao usuário)
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
                preferencias_notificacao JSONB DEFAULT '{}',
                CONSTRAINT fk_cliente_usuario FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
            )
        """)

        # Tabela de configurações do sistema (AGORA multi-tenant)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                id SERIAL PRIMARY KEY,
                chave VARCHAR(100) NOT NULL,
                valor TEXT,
                descricao TEXT,
                chat_id_usuario BIGINT,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_config_por_usuario UNIQUE (chave, chat_id_usuario),
                CONSTRAINT fk_config_usuario FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
            )
        """)

        # Tabela de templates (AGORA multi-tenant)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                descricao TEXT,
                conteudo TEXT NOT NULL,
                tipo VARCHAR(50) DEFAULT 'geral',
                ativo BOOLEAN DEFAULT TRUE,
                uso_count INTEGER DEFAULT 0,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                chat_id_usuario BIGINT,
                CONSTRAINT uq_template_por_usuario UNIQUE (nome, chat_id_usuario),
                CONSTRAINT fk_template_usuario FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
            )
        """)

        # Tabela de logs de envio (AGORA com chat_id_usuario)
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
                data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
            )
        """)

        # Tabela de fila de mensagens (AGORA com chat_id_usuario)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fila_mensagens (
                id SERIAL PRIMARY KEY,
                chat_id_usuario BIGINT,
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
                data_processamento TIMESTAMP,
                FOREIGN KEY (chat_id_usuario) REFERENCES usuarios(chat_id)
            )
        """)

        logger.info("Tabelas criadas/atualizadas com sucesso!")

    def create_indexes(self, cursor):
        """Cria índices para otimização"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_usuarios_chat_id ON usuarios(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_usuarios_status ON usuarios(status)",
            "CREATE INDEX IF NOT EXISTS idx_usuarios_vencimento ON usuarios(proximo_vencimento)",

            "CREATE INDEX IF NOT EXISTS idx_pagamentos_chat_id ON pagamentos(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_pagamentos_status ON pagamentos(status)",

            "CREATE INDEX IF NOT EXISTS idx_clientes_usuario ON clientes(chat_id_usuario)",
            "CREATE INDEX IF NOT EXISTS idx_clientes_telefone ON clientes(telefone)",
            "CREATE INDEX IF NOT EXISTS idx_clientes_vencimento ON clientes(vencimento)",
            "CREATE INDEX IF NOT EXISTS idx_clientes_ativo ON clientes(ativo)",

            "CREATE INDEX IF NOT EXISTS idx_logs_usuario ON logs_envio(chat_id_usuario)",
            "CREATE INDEX IF NOT EXISTS idx_logs_cliente_id ON logs_envio(cliente_id)",
            "CREATE INDEX IF NOT EXISTS idx_logs_data_envio ON logs_envio(data_envio)",

            "CREATE INDEX IF NOT EXISTS idx_fila_agendado ON fila_mensagens(agendado_para)",
            "CREATE INDEX IF NOT EXISTS idx_fila_processado ON fila_mensagens(processado)",
            "CREATE INDEX IF NOT EXISTS idx_fila_usuario ON fila_mensagens(chat_id_usuario)",

            "CREATE INDEX IF NOT EXISTS idx_configuracoes_chave ON configuracoes(chave)",
            "CREATE INDEX IF NOT EXISTS idx_configuracoes_usuario ON configuracoes(chat_id_usuario)",

            "CREATE INDEX IF NOT EXISTS idx_templates_usuario ON templates(chat_id_usuario)"
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)

        logger.info("Índices criados/atualizados com sucesso!")

    # -------------------------
    # Inserts default (globais)
    # -------------------------
    def insert_default_templates(self, cursor):
        """Insere templates padrão do sistema GLOBAIS (chat_id_usuario = NULL)"""
        templates_default = [
            {
                'nome': 'Aviso 2 Dias',
                'descricao': 'Mensagem enviada 2 dias antes do vencimento',
                'tipo': 'vencimento_2dias',
                'conteudo': """🔔 *Lembrete de Vencimento*

Olá {nome}! 👋

Seu plano *{pacote}* vencerá em *2 dias* ({vencimento}).

💰 Valor: *R$ {valor}*
🖥️ Servidor: *{servidor}*

Para renovar, entre em contato conosco ou faça o PIX:

💳 *Chave PIX:* [CONFIGURAR]
💰 *Valor:* R$ {valor}

📞 *Suporte:* [CONFIGURAR]

_Mensagem automática do sistema_ 🤖"""
            },
            {
                'nome': 'Vencimento Hoje',
                'descricao': 'Mensagem enviada no dia do vencimento',
                'tipo': 'vencimento_hoje',
                'conteudo': """⚠️ *VENCIMENTO HOJE*

Olá {nome}! 👋

Seu plano *{pacote}* vence *HOJE* ({vencimento}).

💰 Valor: *R$ {valor}*
🖥️ Servidor: *{servidor}*

⏰ *RENOVAÇÃO URGENTE*

💳 *Chave PIX:* [CONFIGURAR]
💰 *Valor:* R$ {valor}

📞 *Suporte:* [CONFIGURAR]

_Renove hoje para não perder o acesso!_ ⚡"""
            },
            {
                'nome': 'Vencido 1 Dia',
                'descricao': 'Mensagem enviada 1 dia após vencimento',
                'tipo': 'vencimento_1dia_apos',
                'conteudo': """🔴 *PLANO VENCIDO*

Olá {nome}! 👋

Seu plano *{pacote}* venceu ontem ({vencimento}).

💰 Valor: *R$ {valor}*
🖥️ Servidor: *{servidor}*

🚨 *ACESSO SERÁ SUSPENSO EM BREVE*

Para reativar:

💳 *Chave PIX:* [CONFIGURAR]
💰 *Valor:* R$ {valor}

📞 *Suporte:* [CONFIGURAR]

_Regularize sua situação o quanto antes!_ ⚠️"""
            },
            {
                'nome': 'Boas Vindas',
                'descricao': 'Mensagem de boas vindas para novos clientes',
                'tipo': 'boas_vindas',
                'conteudo': """🎉 *BEM-VINDO(A)!*

Olá {nome}! 👋

Seu cadastro foi realizado com sucesso!

📦 *Plano:* {pacote}
💰 *Valor:* R$ {valor}
🖥️ *Servidor:* {servidor}
📅 *Vencimento:* {vencimento}

🔐 *Dados de acesso serão enviados em breve!*

📞 *Suporte:* [CONFIGURAR]

_Obrigado por escolher nossos serviços!_ ✨"""
            },
            {
                'nome': 'Cobrança Manual',
                'descricao': 'Template para cobrança manual personalizada',
                'tipo': 'cobranca_manual',
                'conteudo': """💳 *COBRANÇA*

Olá {nome}! 👋

Referente ao seu plano *{pacote}*:

💰 *Valor:* R$ {valor}
📅 *Vencimento:* {vencimento}
🖥️ *Servidor:* {servidor}

*Dados para pagamento:*

💳 *Chave PIX:* [CONFIGURAR]
💰 *Valor exato:* R$ {valor}

📞 *Suporte:* [CONFIGURAR]

_Envie o comprovante após o pagamento!_ 📄"""
            }
        ]

        for template in templates_default:
            # Verifica se já existe template global (chat_id_usuario = NULL)
            cursor.execute("""
                SELECT COUNT(*) FROM templates 
                WHERE nome = %s AND chat_id_usuario IS NULL
            """, (template['nome'],))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO templates (nome, descricao, tipo, conteudo, chat_id_usuario)
                    VALUES (%(nome)s, %(descricao)s, %(tipo)s, %(conteudo)s, NULL)
                """, template)

        logger.info("Templates padrão inseridos com sucesso!")

    def insert_default_configs(self, cursor):
        """Insere configurações padrão do sistema (globais)"""
        configs_default = [
            ('empresa_nome', 'Sua Empresa IPTV', 'Nome da empresa exibido nas mensagens'),
            ('empresa_pix', '', 'Chave PIX da empresa para pagamentos'),
            ('empresa_titular', '', 'Nome do titular da conta PIX'),
            ('empresa_telefone', '', 'Telefone de contato da empresa'),
            ('baileys_url', 'http://localhost:3000', 'URL da API Baileys WhatsApp'),
            ('baileys_status', 'desconectado', 'Status da conexão com WhatsApp'),
            ('notificacoes_ativas', 'true', 'Se as notificações automáticas estão ativas'),
            ('horario_cobranca', '09:00', 'Horário padrão para envio de cobranças'),
            ('dias_aviso_vencimento', '2', 'Dias de antecedência para avisos de vencimento'),
        ]

        for chave, valor, descricao in configs_default:
            # Verifica se já existe configuração global (chat_id_usuario = NULL)
            cursor.execute("""
                SELECT COUNT(*) FROM configuracoes 
                WHERE chave = %s AND chat_id_usuario IS NULL
            """, (chave,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                    VALUES (%s, %s, %s, NULL)
                """, (chave, valor, descricao))

        logger.info("Configurações padrão inseridas com sucesso!")

    # -------------------------
    # Usuário: criar defaults
    # -------------------------
    def criar_templates_usuario(self, chat_id_usuario):
        """Cria templates personalizados para um usuário específico"""
        try:
            chat_id_usuario = self._require_user(chat_id_usuario)
            templates_usuario = [
                {
                    'nome': f'Aviso 2 Dias - User {chat_id_usuario}',
                    'descricao': 'Mensagem enviada 2 dias antes do vencimento',
                    'tipo': 'vencimento_2dias',
                    'conteudo': """🔔 *Lembrete de Vencimento*

Olá {nome}! 👋

Seu plano *{pacote}* vencerá em *2 dias* ({vencimento}).

💰 Valor: *R$ {valor}*
🖥️ Servidor: *{servidor}*

Para renovar, entre em contato conosco ou faça o PIX:

💳 *Chave PIX:* [Configure sua chave PIX]
💰 *Valor:* R$ {valor}

📞 *Suporte:* [Configure seu telefone]

_Mensagem automática do sistema_ 🤖""",
                    'chat_id_usuario': chat_id_usuario
                },
                {
                    'nome': f'Vencimento Hoje - User {chat_id_usuario}',
                    'descricao': 'Mensagem enviada no dia do vencimento',
                    'tipo': 'vencimento_hoje',
                    'conteudo': """⚠️ *VENCIMENTO HOJE*

Olá {nome}! 👋

Seu plano *{pacote}* vence *HOJE* ({vencimento}).

💰 Valor: *R$ {valor}*
🖥️ Servidor: *{servidor}*

⏰ *RENOVAÇÃO URGENTE*

💳 *Chave PIX:* [Configure sua chave PIX]
💰 *Valor:* R$ {valor}

📞 *Suporte:* [Configure seu telefone]

_Renove hoje para não perder o acesso!_ ⚡""",
                    'chat_id_usuario': chat_id_usuario
                },
                {
                    'nome': f'Vencido 1 Dia - User {chat_id_usuario}',
                    'descricao': 'Mensagem enviada 1 dia após vencimento',
                    'tipo': 'vencimento_1dia_apos',
                    'conteudo': """🔴 *PLANO VENCIDO*

Olá {nome}! 👋

Seu plano *{pacote}* venceu ontem ({vencimento}).

💰 Valor: *R$ {valor}*
🖥️ Servidor: *{servidor}*

🚨 *ACESSO SERÁ SUSPENSO EM BREVE*

Para reativar:

💳 *Chave PIX:* [Configure sua chave PIX]
💰 *Valor:* R$ {valor}

📞 *Suporte:* [Configure seu telefone]

_Regularize sua situação o quanto antes!_ ⚠️""",
                    'chat_id_usuario': chat_id_usuario
                },
                {
                    'nome': f'Boas Vindas - User {chat_id_usuario}',
                    'descricao': 'Mensagem de boas vindas para novos clientes',
                    'tipo': 'boas_vindas',
                    'conteudo': """🎉 *BEM-VINDO(A)!*

Olá {nome}! 👋

Seu cadastro foi realizado com sucesso!

📦 *Plano:* {pacote}
💰 *Valor:* R$ {valor}
🖥️ *Servidor:* {servidor}
📅 *Vencimento:* {vencimento}

🔐 *Dados de acesso serão enviados em breve!*

📞 *Suporte:* [Configure seu telefone]

_Obrigado por escolher nossos serviços!_ ✨""",
                    'chat_id_usuario': chat_id_usuario
                }
            ]

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    for template in templates_usuario:
                        cursor.execute("""
                            INSERT INTO templates (nome, descricao, tipo, conteudo, chat_id_usuario)
                            VALUES (%(nome)s, %(descricao)s, %(tipo)s, %(conteudo)s, %(chat_id_usuario)s)
                        """, template)
                    conn.commit()

            logger.info(f"Templates personalizados criados para usuário {chat_id_usuario}")

        except Exception as e:
            logger.error(f"Erro ao criar templates do usuário: {e}")
            raise

    def criar_configuracoes_usuario(self, chat_id_usuario, nome_usuario):
        """Cria configurações personalizadas para um usuário específico"""
        try:
            chat_id_usuario = self._require_user(chat_id_usuario)
            configs_usuario = [
                ('empresa_nome', f'{nome_usuario} IPTV', 'Nome da empresa exibido nas mensagens'),
                ('empresa_pix', '', 'Chave PIX da empresa para pagamentos'),
                ('empresa_titular', nome_usuario, 'Nome do titular da conta PIX'),
                ('empresa_telefone', '', 'Telefone de contato da empresa'),
                ('baileys_url', 'http://localhost:3000', 'URL da API Baileys WhatsApp'),
                ('baileys_status', 'desconectado', 'Status da conexão com WhatsApp'),
                ('notificacoes_ativas', 'true', 'Se as notificações automáticas estão ativas'),
                ('horario_cobranca', '09:00', 'Horário padrão para envio de cobranças'),
                ('dias_aviso_vencimento', '2', 'Dias de antecedência para avisos de vencimento'),
            ]

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    for chave, valor, descricao in configs_usuario:
                        cursor.execute("""
                            INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (chave, chat_id_usuario) DO UPDATE
                              SET valor = EXCLUDED.valor,
                                  descricao = COALESCE(EXCLUDED.descricao, configuracoes.descricao),
                                  data_atualizacao = CURRENT_TIMESTAMP
                        """, (chave, valor, descricao, chat_id_usuario))
                    conn.commit()

            logger.info(f"Configurações personalizadas criadas para usuário {chat_id_usuario}")

        except Exception as e:
            logger.error(f"Erro ao criar configurações do usuário: {e}")
            raise

    # -------------------------
    # CLIENTES (sempre isolado)
    # -------------------------
    def cadastrar_cliente(self, nome, telefone, pacote, valor, servidor, vencimento, chat_id_usuario=None, info_adicional=None):
        """Cadastra novo cliente e invalida cache (isolado por usuário)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO clientes (chat_id_usuario, nome, telefone, pacote, valor, servidor, vencimento, info_adicional)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (chat_id_usuario, nome, telefone, pacote, valor, servidor, vencimento, info_adicional))

                    cliente_id = cursor.fetchone()[0]
                    conn.commit()

                    # Invalidar cache de clientes
                    self.invalidate_cache("clientes")

                    logger.info(f"Cliente cadastrado: ID {cliente_id}, Nome: {nome}")
                    return cliente_id

        except Exception as e:
            logger.error(f"Erro ao cadastrar cliente: {e}")
            raise

    def criar_cliente(self, *args, **kwargs):
        """Alias para cadastrar_cliente (compatibilidade)"""
        return self.cadastrar_cliente(*args, **kwargs)

    def listar_clientes(self, apenas_ativos=True, limit=None, chat_id_usuario=None):
        """Lista clientes com informações de vencimento (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        cache_key = f"clientes_{apenas_ativos}_{limit}_{chat_id_usuario}"

        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where_conditions = ["chat_id_usuario = %s"]
                    params = [chat_id_usuario]

                    if apenas_ativos:
                        where_conditions.append("ativo = TRUE")

                    where_clause = "WHERE " + " AND ".join(where_conditions)
                    limit_clause = f"LIMIT {limit}" if limit else ""

                    cursor.execute(f"""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro, info_adicional, chat_id_usuario,
                            (vencimento - CURRENT_DATE) as dias_vencimento,
                            CASE 
                                WHEN vencimento < CURRENT_DATE THEN 'vencido'
                                WHEN vencimento = CURRENT_DATE THEN 'vence_hoje'
                                WHEN vencimento <= CURRENT_DATE + INTERVAL '3 days' THEN 'vence_em_breve'
                                ELSE 'em_dia'
                            END as status_vencimento
                        FROM clientes 
                        {where_clause}
                        ORDER BY vencimento ASC, nome ASC
                        {limit_clause}
                    """, params)

                    clientes = cursor.fetchall()
                    result = [dict(cliente) for cliente in clientes]

                    if len(result) < 1000:
                        self._set_cache(cache_key, result)

                    return result

        except Exception as e:
            logger.error(f"Erro ao listar clientes: {e}")
            raise

    def invalidate_cache(self, pattern=None):
        """Invalida cache específico ou todos"""
        if pattern:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]
                if key in self._cache_ttl:
                    del self._cache_ttl[key]
        else:
            self._cache.clear()
            self._cache_ttl.clear()

    def buscar_cliente_por_id(self, cliente_id, chat_id_usuario=None):
        """Busca cliente por ID - ISOLADO POR USUÁRIO"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro, data_atualizacao, info_adicional,
                            chat_id_usuario, receber_cobranca, receber_notificacoes,
                            preferencias_notificacao,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE id = %s AND chat_id_usuario = %s
                    """, (cliente_id, chat_id_usuario))

                    cliente = cursor.fetchone()
                    return dict(cliente) if cliente else None

        except Exception as e:
            logger.error(f"Erro ao buscar cliente por ID: {e}")
            raise

    def buscar_cliente_por_telefone(self, telefone, chat_id_usuario=None):
        """Busca cliente por telefone - ISOLADO POR USUÁRIO"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro, chat_id_usuario,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE telefone = %s AND ativo = TRUE AND chat_id_usuario = %s
                        ORDER BY data_cadastro DESC
                        LIMIT 1
                    """, (telefone, chat_id_usuario))

                    cliente = cursor.fetchone()
                    return dict(cliente) if cliente else None

        except Exception as e:
            logger.error(f"Erro ao buscar cliente por telefone: {e}")
            raise

    def buscar_clientes_por_telefone(self, telefone, chat_id_usuario=None):
        """Busca todos os clientes com o mesmo telefone (do usuário)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE telefone = %s AND ativo = TRUE AND chat_id_usuario = %s
                        ORDER BY vencimento ASC
                    """, (telefone, chat_id_usuario))

                    clientes = cursor.fetchall()
                    return [dict(cliente) for cliente in clientes]

        except Exception as e:
            logger.error(f"Erro ao buscar clientes por telefone: {e}")
            raise

    def atualizar_vencimento_cliente(self, cliente_id, novo_vencimento, chat_id_usuario=None):
        """Atualiza data de vencimento do cliente (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE clientes 
                        SET vencimento = %s, data_atualizacao = CURRENT_TIMESTAMP
                        WHERE id = %s AND ativo = TRUE AND chat_id_usuario = %s
                    """, (novo_vencimento, cliente_id, chat_id_usuario))

                    if cursor.rowcount == 0:
                        raise ValueError("Cliente não encontrado, inativo ou não pertence ao usuário")

                    conn.commit()
                    logger.info(f"Vencimento atualizado para cliente ID {cliente_id}: {novo_vencimento}")

        except Exception as e:
            logger.error(f"Erro ao atualizar vencimento: {e}")
            raise

    def excluir_cliente(self, cliente_id, chat_id_usuario=None):
        """Exclui cliente definitivamente (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Excluir logs relacionados do mesmo usuário
                    cursor.execute("""
                        DELETE FROM logs_envio 
                        WHERE cliente_id = %s AND chat_id_usuario = %s
                    """, (cliente_id, chat_id_usuario))

                    # Excluir mensagens na fila do mesmo usuário
                    cursor.execute("""
                        DELETE FROM fila_mensagens 
                        WHERE cliente_id = %s AND chat_id_usuario = %s
                    """, (cliente_id, chat_id_usuario))

                    # Finalmente, excluir o cliente
                    cursor.execute("""
                        DELETE FROM clientes 
                        WHERE id = %s AND chat_id_usuario = %s
                    """, (cliente_id, chat_id_usuario))

                    if cursor.rowcount == 0:
                        raise ValueError("Cliente não encontrado ou não pertence ao usuário")

                    conn.commit()
                    logger.info(f"Cliente ID {cliente_id} excluído definitivamente")

        except Exception as e:
            logger.error(f"Erro ao excluir cliente: {e}")
            raise

    def buscar_clientes(self, termo, chat_id_usuario=None):
        """Busca clientes por nome ou telefone (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro, chat_id_usuario,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE chat_id_usuario = %s
                          AND ativo = TRUE
                          AND (LOWER(nome) LIKE LOWER(%s) OR telefone LIKE %s)
                        ORDER BY nome ASC
                        LIMIT 20
                    """, (chat_id_usuario, f'%{termo}%', f'%{termo}%'))

                    clientes = cursor.fetchall()
                    return [dict(cliente) for cliente in clientes]

        except Exception as e:
            logger.error(f"Erro ao buscar clientes: {e}")
            raise

    def listar_clientes_vencendo(self, dias=3, chat_id_usuario=None):
        """Lista clientes com vencimento próximo (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Postgres não aceita bind dentro de 'INTERVAL %s days'
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE chat_id_usuario = %s
                          AND ativo = TRUE
                          AND vencimento <= CURRENT_DATE + (%s * INTERVAL '1 day')
                        ORDER BY vencimento ASC
                    """, (chat_id_usuario, dias))

                    clientes = cursor.fetchall()
                    return [dict(cliente) for cliente in clientes]

        except Exception as e:
            logger.error(f"Erro ao listar clientes vencendo: {e}")
            raise

    def atualizar_cliente(self, cliente_id, chat_id_usuario=None, **kwargs):
        """Atualiza dados do cliente (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    campos = []
                    valores = []

                    for campo, valor in kwargs.items():
                        if valor is not None:
                            campos.append(f"{campo} = %s")
                            valores.append(valor)

                    if not campos:
                        return False

                    campos.append("data_atualizacao = CURRENT_TIMESTAMP")
                    valores.extend([cliente_id, chat_id_usuario])

                    query = f"""
                        UPDATE clientes 
                        SET {', '.join(campos)}
                        WHERE id = %s AND chat_id_usuario = %s
                    """

                    cursor.execute(query, valores)
                    conn.commit()

                    return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Erro ao atualizar cliente: {e}")
            raise

    def desativar_cliente(self, cliente_id, chat_id_usuario=None):
        """Desativa cliente (soft delete)"""
        return self.atualizar_cliente(cliente_id, chat_id_usuario=chat_id_usuario, ativo=False)

    def reativar_cliente(self, cliente_id, chat_id_usuario=None):
        """Reativa cliente"""
        return self.atualizar_cliente(cliente_id, chat_id_usuario=chat_id_usuario, ativo=True)

    # -------------------------
    # Preferências de notificação (ISOLADO)
    # -------------------------
    def atualizar_preferencias_cliente(self, cliente_id, chat_id_usuario=None, receber_cobranca=None, receber_notificacoes=None, preferencias_extras=None):
        """Atualiza preferências de notificação de um cliente"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            dados_update = {}

            if receber_cobranca is not None:
                dados_update['receber_cobranca'] = receber_cobranca

            if receber_notificacoes is not None:
                dados_update['receber_notificacoes'] = receber_notificacoes

            if preferencias_extras is not None:
                import json
                dados_update['preferencias_notificacao'] = json.dumps(preferencias_extras) if isinstance(preferencias_extras, dict) else preferencias_extras

            if not dados_update:
                return False

            campos_set = []
            valores = []

            for campo, valor in dados_update.items():
                campos_set.append(f"{campo} = %s")
                valores.append(valor)

            campos_set.append("data_atualizacao = CURRENT_TIMESTAMP")
            valores.extend([cliente_id, chat_id_usuario])

            query = f"""
                UPDATE clientes 
                SET {', '.join(campos_set)}
                WHERE id = %s AND chat_id_usuario = %s
            """

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, valores)
                    conn.commit()

                    success = cursor.rowcount > 0
                    if success:
                        logger.info(f"Preferências atualizadas para cliente ID {cliente_id}")

                    return success

        except Exception as e:
            logger.error(f"Erro ao atualizar preferências do cliente: {e}")
            raise

    def obter_preferencias_cliente(self, cliente_id, chat_id_usuario=None):
        """Obtém preferências de notificação de um cliente (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    query = """
                        SELECT 
                            id, nome, receber_cobranca, receber_notificacoes, 
                            preferencias_notificacao
                        FROM clientes 
                        WHERE id = %s AND chat_id_usuario = %s
                    """
                    params = [cliente_id, chat_id_usuario]

                    cursor.execute(query, params)
                    resultado = cursor.fetchone()

                    if resultado:
                        dados = dict(resultado)
                        # Converter JSON de preferencias_notificacao se necessário
                        if dados.get('preferencias_notificacao'):
                            import json
                            try:
                                dados['preferencias_notificacao'] = json.loads(dados['preferencias_notificacao'])
                            except Exception:
                                dados['preferencias_notificacao'] = {}
                        else:
                            dados['preferencias_notificacao'] = {}

                        return dados

                    return None

        except Exception as e:
            logger.error(f"Erro ao obter preferências do cliente: {e}")
            raise

    def cliente_pode_receber_cobranca(self, cliente_id, chat_id_usuario=None):
        """Verifica se cliente pode receber mensagens de cobrança"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            prefs = self.obter_preferencias_cliente(cliente_id, chat_id_usuario)
            return prefs.get('receber_cobranca', True) if prefs else False
        except Exception as e:
            logger.error(f"Erro ao verificar preferências de cobrança: {e}")
            return False

    def cliente_pode_receber_notificacoes(self, cliente_id, chat_id_usuario=None):
        """Verifica se cliente pode receber notificações gerais"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            prefs = self.obter_preferencias_cliente(cliente_id, chat_id_usuario)
            return prefs.get('receber_notificacoes', True) if prefs else False
        except Exception as e:
            logger.error(f"Erro ao verificar preferências de notificação: {e}")
            return False

    def listar_clientes_notificacao(self, tipo_notificacao='cobranca', chat_id_usuario=None):
        """Lista clientes que podem receber determinado tipo de notificação (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            campo_verificacao = 'receber_cobranca' if tipo_notificacao == 'cobranca' else 'receber_notificacoes'

            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    query = f"""
                        SELECT 
                            id, nome, telefone, pacote, valor, vencimento,
                            {campo_verificacao}, receber_notificacoes, receber_cobranca
                        FROM clientes 
                        WHERE ativo = TRUE AND {campo_verificacao} = TRUE
                          AND chat_id_usuario = %s
                        ORDER BY nome ASC
                    """
                    cursor.execute(query, (chat_id_usuario,))
                    clientes = cursor.fetchall()
                    return [dict(cliente) for cliente in clientes]

        except Exception as e:
            logger.error(f"Erro ao listar clientes para notificação: {e}")
            raise

    # -------------------------
    # TEMPLATES (isolado + globais opcionais)
    # -------------------------
    def listar_templates(self, apenas_ativos=True, chat_id_usuario=None, incluir_globais=True):
        """Lista templates do usuário; opcionalmente inclui os globais (NULL)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where = []
                    params = []

                    if apenas_ativos:
                        where.append("ativo = TRUE")

                    if incluir_globais:
                        where.append("(chat_id_usuario = %s OR chat_id_usuario IS NULL)")
                        params.append(chat_id_usuario)
                    else:
                        where.append("chat_id_usuario = %s")
                        params.append(chat_id_usuario)

                    where_clause = "WHERE " + " AND ".join(where) if where else ""

                    cursor.execute(f"""
                        SELECT id, nome, descricao, conteudo, tipo, ativo, uso_count,
                               data_criacao, data_atualizacao, chat_id_usuario
                        FROM templates 
                        {where_clause}
                        ORDER BY (chat_id_usuario IS NULL), nome ASC
                    """, params)

                    templates = cursor.fetchall()
                    return [dict(template) for template in templates]

        except Exception as e:
            logger.error(f"Erro ao listar templates: {e}")
            raise

    def obter_template(self, template_id, chat_id_usuario=None):
        """Obtém template por ID (usuário ou global)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(f"""
                        SELECT id, nome, descricao, conteudo, tipo, ativo, uso_count, chat_id_usuario
                        FROM templates 
                        WHERE id = %s AND (chat_id_usuario = %s OR chat_id_usuario IS NULL)
                    """, (template_id, chat_id_usuario))

                    template = cursor.fetchone()
                    return dict(template) if template else None

        except Exception as e:
            logger.error(f"Erro ao obter template: {e}")
            raise

    def obter_template_por_tipo(self, tipo, chat_id_usuario=None):
        """Obtém template por tipo (usuário ou global)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(f"""
                        SELECT id, nome, descricao, conteudo, tipo, ativo, uso_count, chat_id_usuario
                        FROM templates 
                        WHERE tipo = %s AND ativo = TRUE
                          AND (chat_id_usuario = %s OR chat_id_usuario IS NULL)
                        ORDER BY (chat_id_usuario IS NULL) ASC
                        LIMIT 1
                    """, (tipo, chat_id_usuario))

                    template = cursor.fetchone()
                    return dict(template) if template else None

        except Exception as e:
            logger.error(f"Erro ao obter template por tipo: {e}")
            raise

    def buscar_template_por_id(self, template_id, chat_id_usuario=None):
        """Alias para compatibilidade"""
        return self.obter_template(template_id, chat_id_usuario=chat_id_usuario)

    def excluir_template(self, template_id, chat_id_usuario=None):
        """Exclui template definitivamente (apenas do usuário; não remove globais)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Verifica se pertence ao usuário
                    cursor.execute("""
                        SELECT id FROM templates WHERE id = %s AND chat_id_usuario = %s
                    """, (template_id, chat_id_usuario))
                    if cursor.fetchone() is None:
                        raise ValueError("Template não encontrado ou não pertence ao usuário (templates globais não podem ser excluídos)")

                    # Remover logs e fila deste usuário com esse template
                    cursor.execute("DELETE FROM logs_envio WHERE template_id = %s AND chat_id_usuario = %s", (template_id, chat_id_usuario))
                    cursor.execute("DELETE FROM fila_mensagens WHERE template_id = %s AND chat_id_usuario = %s", (template_id, chat_id_usuario))

                    # Excluir template do usuário
                    cursor.execute("DELETE FROM templates WHERE id = %s AND chat_id_usuario = %s", (template_id, chat_id_usuario))

                    conn.commit()
                    logger.info(f"Template ID {template_id} excluído definitivamente para usuário {chat_id_usuario}")

        except Exception as e:
            logger.error(f"Erro ao excluir template: {e}")
            raise

    def criar_template(self, nome, descricao, conteudo, tipo='geral', chat_id_usuario=None):
        """Cria novo template do usuário"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO templates (nome, descricao, conteudo, tipo, chat_id_usuario)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                    """, (nome, descricao, conteudo, tipo, chat_id_usuario))

                    template_id = cursor.fetchone()[0]
                    conn.commit()

                    logger.info(f"Template criado: ID {template_id}, Nome: {nome}, Usuário: {chat_id_usuario}")
                    return template_id

        except Exception as e:
            logger.error(f"Erro ao criar template: {e}")
            raise

    def atualizar_template(self, template_id, chat_id_usuario=None, nome=None, descricao=None, conteudo=None):
        """Atualiza template do usuário"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    campos = []
                    valores = []

                    if nome is not None:
                        campos.append("nome = %s")
                        valores.append(nome)

                    if descricao is not None:
                        campos.append("descricao = %s")
                        valores.append(descricao)

                    if conteudo is not None:
                        campos.append("conteudo = %s")
                        valores.append(conteudo)

                    if not campos:
                        return False

                    campos.append("data_atualizacao = CURRENT_TIMESTAMP")
                    valores.extend([template_id, chat_id_usuario])

                    query = f"""
                        UPDATE templates 
                        SET {', '.join(campos)}
                        WHERE id = %s AND chat_id_usuario = %s
                    """

                    cursor.execute(query, valores)
                    conn.commit()

                    return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Erro ao atualizar template: {e}")
            raise

    def atualizar_template_campo(self, template_id, campo, valor, chat_id_usuario=None):
        """Atualiza campo específico do template do usuário"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            campos_validos = ['nome', 'descricao', 'conteudo', 'tipo', 'ativo']
            if campo not in campos_validos:
                raise ValueError(f"Campo '{campo}' não é válido. Use: {', '.join(campos_validos)}")

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = f"""
                        UPDATE templates 
                        SET {campo} = %s, data_atualizacao = CURRENT_TIMESTAMP
                        WHERE id = %s AND chat_id_usuario = %s
                    """

                    cursor.execute(query, (valor, template_id, chat_id_usuario))
                    conn.commit()

                    if cursor.rowcount == 0:
                        logger.warning(f"Template ID {template_id} não encontrado para atualização ou não pertence ao usuário")
                        return False

                    logger.info(f"Template ID {template_id} - campo '{campo}' atualizado")
                    return True

        except Exception as e:
            logger.error(f"Erro ao atualizar campo do template: {e}")
            raise

    def incrementar_uso_template(self, template_id, chat_id_usuario=None):
        """Incrementa contador de uso do template (do usuário ou global acessível)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE templates 
                        SET uso_count = uso_count + 1
                        WHERE id = %s AND (chat_id_usuario = %s OR chat_id_usuario IS NULL)
                    """, (template_id, chat_id_usuario))
                    conn.commit()

        except Exception as e:
            logger.error(f"Erro ao incrementar uso do template: {e}")

    # -------------------------
    # LOGS (ISOLADO)
    # -------------------------
    def registrar_envio(self, cliente_id, template_id, telefone, mensagem, tipo_envio, sucesso, erro=None, message_id=None, chat_id_usuario=None):
        """Registra log de envio de mensagem (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO logs_envio 
                        (chat_id_usuario, cliente_id, template_id, telefone, mensagem, tipo_envio, sucesso, erro, message_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (chat_id_usuario, cliente_id, template_id, telefone, mensagem, tipo_envio, sucesso, erro, message_id))

                    log_id = cursor.fetchone()[0]
                    conn.commit()

                    if sucesso and template_id:
                        self.incrementar_uso_template(template_id, chat_id_usuario=chat_id_usuario)

                    return log_id

        except Exception as e:
            logger.error(f"Erro ao registrar envio: {e}")
            raise

    def registrar_envio_manual(self, cliente_id, template_id, mensagem, chat_id_usuario=None):
        """Registra envio manual (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        cliente = self.buscar_cliente_por_id(cliente_id, chat_id_usuario=chat_id_usuario)
        return self.registrar_envio(
            cliente_id=cliente_id,
            template_id=template_id,
            telefone=cliente['telefone'],
            mensagem=mensagem,
            tipo_envio='manual',
            sucesso=True,
            chat_id_usuario=chat_id_usuario
        )

    def obter_logs_envios(self, chat_id_usuario=None, cliente_id=None, limit=50):
        """Obtém logs de envios (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where = ["l.chat_id_usuario = %s"]
                    params = [chat_id_usuario]
                    if cliente_id:
                        where.append("l.cliente_id = %s")
                        params.append(cliente_id)
                    where_clause = "WHERE " + " AND ".join(where)

                    cursor.execute(f"""
                        SELECT 
                            l.id, l.cliente_id, l.template_id, l.telefone, l.mensagem,
                            l.tipo_envio, l.sucesso, l.erro, l.message_id, l.data_envio,
                            c.nome as cliente_nome,
                            t.nome as template_nome
                        FROM logs_envio l
                        LEFT JOIN clientes c ON l.cliente_id = c.id
                        LEFT JOIN templates t ON l.template_id = t.id
                        {where_clause}
                        ORDER BY l.data_envio DESC
                        LIMIT %s
                    """, (*params, limit))

                    logs = cursor.fetchall()
                    return [dict(log) for log in logs]

        except Exception as e:
            logger.error(f"Erro ao obter logs: {e}")
            raise

    # -------------------------
    # FILA (ISOLADO)
    # -------------------------
    def adicionar_fila_mensagem(self, cliente_id, template_id, telefone, mensagem, tipo_mensagem, agendado_para, chat_id_usuario=None):
        """Adiciona mensagem na fila de envio (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO fila_mensagens 
                        (chat_id_usuario, cliente_id, template_id, telefone, mensagem, tipo_mensagem, agendado_para)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (chat_id_usuario, cliente_id, template_id, telefone, mensagem, tipo_mensagem, agendado_para))

                    fila_id = cursor.fetchone()[0]
                    conn.commit()

                    logger.info(f"Mensagem adicionada à fila: ID {fila_id}")
                    return fila_id

        except Exception as e:
            logger.error(f"Erro ao adicionar mensagem na fila: {e}")
            raise

    def obter_mensagens_pendentes(self, chat_id_usuario=None, limit=100):
        """Obtém mensagens pendentes para envio (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            f.id, f.cliente_id, f.template_id, f.telefone, f.mensagem,
                            f.tipo_mensagem, f.agendado_para, f.tentativas, f.max_tentativas,
                            c.nome as cliente_nome
                        FROM fila_mensagens f
                        LEFT JOIN clientes c ON f.cliente_id = c.id
                        WHERE f.chat_id_usuario = %s
                          AND f.processado = FALSE 
                          AND f.agendado_para <= CURRENT_TIMESTAMP
                          AND f.tentativas < f.max_tentativas
                        ORDER BY f.agendado_para ASC
                        LIMIT %s
                    """, (chat_id_usuario, limit))

                    mensagens = cursor.fetchall()
                    return [dict(msg) for msg in mensagens]

        except Exception as e:
            logger.error(f"Erro ao obter mensagens pendentes: {e}")
            raise

    def marcar_mensagem_processada(self, fila_id, sucesso, chat_id_usuario=None, erro=None):
        """Marca mensagem como processada (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    if sucesso:
                        cursor.execute("""
                            UPDATE fila_mensagens 
                            SET processado = TRUE, data_processamento = CURRENT_TIMESTAMP
                            WHERE id = %s AND chat_id_usuario = %s
                        """, (fila_id, chat_id_usuario))
                    else:
                        cursor.execute("""
                            UPDATE fila_mensagens 
                            SET tentativas = tentativas + 1
                            WHERE id = %s AND chat_id_usuario = %s
                        """, (fila_id, chat_id_usuario))

                    conn.commit()

        except Exception as e:
            logger.error(f"Erro ao marcar mensagem processada: {e}")
            raise

    def limpar_fila_processadas(self, dias=7, chat_id_usuario=None):
        """Remove mensagens processadas antigas da fila (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM fila_mensagens 
                        WHERE processado = TRUE 
                          AND data_processamento < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                          AND chat_id_usuario = %s
                    """, (dias, chat_id_usuario))

                    removidas = cursor.rowcount
                    conn.commit()

                    logger.info(f"Removidas {removidas} mensagens antigas da fila para usuário {chat_id_usuario}")
                    return removidas

        except Exception as e:
            logger.error(f"Erro ao limpar fila: {e}")
            raise

    def limpar_mensagens_futuras(self, chat_id_usuario=None):
        """Remove mensagens agendadas para envio futuro (mais de 1 dia) (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM fila_mensagens 
                        WHERE processado = FALSE 
                          AND agendado_para > CURRENT_TIMESTAMP + INTERVAL '1 day'
                          AND chat_id_usuario = %s
                    """, (chat_id_usuario,))

                    removidas = cursor.rowcount
                    conn.commit()

                    logger.info(f"Removidas {removidas} mensagens agendadas para futuro distante (user {chat_id_usuario})")
                    return removidas

        except Exception as e:
            logger.error(f"Erro ao limpar mensagens futuras: {e}")
            raise

    def obter_todas_mensagens_fila(self, chat_id_usuario=None, limit=50):
        """Obtém todas as mensagens da fila (pendentes e futuras) (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            f.id, f.cliente_id, f.template_id, f.telefone, f.mensagem,
                            f.tipo_mensagem, f.agendado_para, f.tentativas, f.max_tentativas,
                            f.processado, f.data_criacao,
                            c.nome as cliente_nome, c.pacote
                        FROM fila_mensagens f
                        LEFT JOIN clientes c ON f.cliente_id = c.id
                        WHERE f.chat_id_usuario = %s
                        ORDER BY f.agendado_para ASC
                        LIMIT %s
                    """, (chat_id_usuario, limit))

                    mensagens = cursor.fetchall()
                    return [dict(msg) for msg in mensagens]

        except Exception as e:
            logger.error(f"Erro ao obter mensagens da fila: {e}")
            raise

    def buscar_mensagens_fila_cliente(self, cliente_id, chat_id_usuario=None, apenas_pendentes=True):
        """Busca mensagens na fila de um cliente específico (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            params = [chat_id_usuario, cliente_id]
            where = "WHERE f.chat_id_usuario = %s AND f.cliente_id = %s"
            if apenas_pendentes:
                where += " AND f.processado = FALSE"
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(f"""
                        SELECT 
                            f.id, f.cliente_id, f.template_id, f.telefone, f.mensagem,
                            f.tipo_mensagem, f.agendado_para, f.tentativas, f.max_tentativas,
                            f.processado, f.data_criacao,
                            c.nome as cliente_nome, c.pacote
                        FROM fila_mensagens f
                        LEFT JOIN clientes c ON f.cliente_id = c.id
                        {where}
                        ORDER BY f.agendado_para ASC
                    """, params)
                    mensagens = cursor.fetchall()
                    return [dict(msg) for msg in mensagens]

        except Exception as e:
            logger.error(f"Erro ao buscar mensagens da fila do cliente {cliente_id}: {e}")
            raise

    def verificar_mensagem_existente(self, cliente_id, template_id, data_envio, chat_id_usuario=None):
        """Verifica se já existe uma mensagem agendada para o cliente/data (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id FROM fila_mensagens 
                        WHERE cliente_id = %s 
                          AND template_id = %s 
                          AND DATE(agendado_para) = %s 
                          AND processado = FALSE
                          AND chat_id_usuario = %s
                        LIMIT 1
                    """, (cliente_id, template_id, data_envio, chat_id_usuario))

                    resultado = cursor.fetchone()
                    return resultado is not None

        except Exception as e:
            logger.error(f"Erro ao verificar mensagem existente: {e}")
            return False

    # -------------------------
    # ESTATÍSTICAS (ISOLADO)
    # -------------------------
    def obter_estatisticas(self, chat_id_usuario=None):
        """Obtém estatísticas gerais do sistema (ISOLADO por usuário)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    stats = {}

                    # Total de clientes ativos
                    cursor.execute("SELECT COUNT(*) FROM clientes WHERE ativo = TRUE AND chat_id_usuario = %s", (chat_id_usuario,))
                    stats['total_clientes'] = cursor.fetchone()[0]

                    # Novos clientes este mês
                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE 
                          AND chat_id_usuario = %s
                          AND data_cadastro >= date_trunc('month', CURRENT_DATE)
                    """, (chat_id_usuario,))
                    stats['novos_mes'] = cursor.fetchone()[0]

                    # Receita mensal (soma valores dos clientes ativos)
                    cursor.execute("""
                        SELECT COALESCE(SUM(valor), 0) FROM clientes 
                        WHERE ativo = TRUE AND chat_id_usuario = %s
                    """, (chat_id_usuario,))
                    stats['receita_mensal'] = float(cursor.fetchone()[0])
                    stats['receita_anual'] = stats['receita_mensal'] * 12

                    # Vencimentos
                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE AND vencimento < CURRENT_DATE
                          AND chat_id_usuario = %s
                    """, (chat_id_usuario,))
                    stats['vencidos'] = cursor.fetchone()[0]

                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE AND vencimento = CURRENT_DATE
                          AND chat_id_usuario = %s
                    """, (chat_id_usuario,))
                    stats['vencem_hoje'] = cursor.fetchone()[0]

                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE 
                          AND chat_id_usuario = %s
                          AND vencimento BETWEEN CURRENT_DATE + INTERVAL '1 day' 
                          AND CURRENT_DATE + INTERVAL '3 days'
                    """, (chat_id_usuario,))
                    stats['vencem_3dias'] = cursor.fetchone()[0]

                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE 
                          AND chat_id_usuario = %s
                          AND vencimento BETWEEN CURRENT_DATE 
                          AND CURRENT_DATE + INTERVAL '7 days'
                    """, (chat_id_usuario,))
                    stats['vencem_semana'] = cursor.fetchone()[0]

                    # Mensagens hoje
                    cursor.execute("""
                        SELECT COUNT(*) FROM logs_envio 
                        WHERE DATE(data_envio) = CURRENT_DATE
                          AND chat_id_usuario = %s
                    """, (chat_id_usuario,))
                    stats['mensagens_hoje'] = cursor.fetchone()[0]

                    # Fila de mensagens
                    cursor.execute("""
                        SELECT COUNT(*) FROM fila_mensagens 
                        WHERE processado = FALSE AND chat_id_usuario = %s
                    """, (chat_id_usuario,))
                    stats['fila_mensagens'] = cursor.fetchone()[0]

                    # Templates ativos (próprios + globais)
                    cursor.execute("""
                        SELECT COUNT(*) FROM templates 
                        WHERE ativo = TRUE AND (chat_id_usuario = %s OR chat_id_usuario IS NULL)
                    """, (chat_id_usuario,))
                    stats['total_templates'] = cursor.fetchone()[0]

                    cursor.execute("""
                        SELECT nome FROM templates 
                        WHERE ativo = TRUE AND (chat_id_usuario = %s OR chat_id_usuario IS NULL)
                        ORDER BY uso_count DESC 
                        LIMIT 1
                    """, (chat_id_usuario,))
                    resultado = cursor.fetchone()
                    stats['template_mais_usado'] = resultado[0] if resultado else 'Nenhum'

                    return stats

        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            raise

    # -------------------------
    # CONFIGURAÇÕES (preferir usuário; cai para global)
    # -------------------------
    def obter_configuracao(self, chave, valor_padrao=None, chat_id_usuario=None):
        """Obtém valor de configuração com isolamento por usuário; fallback para global"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Se chat_id_usuario fornecido, busca configuração específica do usuário primeiro
                    if chat_id_usuario is not None:
                        cursor.execute("""
                            SELECT valor FROM configuracoes 
                            WHERE chave = %s AND chat_id_usuario = %s
                        """, (chave, chat_id_usuario))
                        resultado = cursor.fetchone()
                        if resultado:
                            return resultado[0]

                    # Se não encontrou ou não foi especificado usuário, busca configuração global
                    cursor.execute("""
                        SELECT valor FROM configuracoes 
                        WHERE chave = %s AND chat_id_usuario IS NULL
                    """, (chave,))
                    resultado = cursor.fetchone()
                    return resultado[0] if resultado else valor_padrao

        except Exception as e:
            logger.error(f"Erro ao obter configuração: {e}")
            return valor_padrao

    def salvar_configuracao(self, chave, valor, descricao=None):
        """Salva configuração global (ou atualiza)"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                        VALUES (%s, %s, %s, NULL)
                        ON CONFLICT (chave, chat_id_usuario) 
                        DO UPDATE SET 
                            valor = EXCLUDED.valor,
                            descricao = COALESCE(EXCLUDED.descricao, configuracoes.descricao),
                            data_atualizacao = CURRENT_TIMESTAMP
                    """, (chave, valor, descricao))

                    conn.commit()

        except Exception as e:
            logger.error(f"Erro ao salvar configuração: {e}")
            raise

    def salvar_configuracao_usuario(self, chave, valor, chat_id_usuario=None, descricao=None):
        """Salva configuração para um usuário específico (isolado)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (chave, chat_id_usuario) 
                        DO UPDATE SET 
                            valor = EXCLUDED.valor,
                            descricao = COALESCE(EXCLUDED.descricao, configuracoes.descricao),
                            data_atualizacao = CURRENT_TIMESTAMP
                    """, (chave, valor, descricao, chat_id_usuario))

                    conn.commit()

        except Exception as e:
            logger.error(f"Erro ao salvar configuração do usuário: {e}")
            raise

    def cancelar_mensagem_fila(self, mensagem_id, chat_id_usuario=None):
        """Cancela uma mensagem agendada da fila (ISOLADO)"""
        chat_id_usuario = self._require_user(chat_id_usuario)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM fila_mensagens 
                        WHERE id = %s AND processado = FALSE AND chat_id_usuario = %s
                        RETURNING cliente_id, tipo_mensagem
                    """, (mensagem_id, chat_id_usuario))

                    resultado = cursor.fetchone()
                    if not resultado:
                        return False

                    conn.commit()
                    logger.info(f"Mensagem ID {mensagem_id} cancelada da fila (user {chat_id_usuario})")
                    return True

        except Exception as e:
            logger.error(f"Erro ao cancelar mensagem da fila: {e}")
            raise

    def obter_todas_mensagens_fila(self, chat_id_usuario=None, limit=50):
        """(Mantido acima) - alias para compatibilidade se for chamado externamente"""
        return self.obter_todas_mensagens_fila(chat_id_usuario=chat_id_usuario, limit=limit)

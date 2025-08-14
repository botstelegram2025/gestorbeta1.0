"""
Gerenciador de Banco de Dados PostgreSQL
Sistema completo para gestão de clientes, templates e logs
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime, timedelta
from utils import agora_br, formatar_data_br
from models import Cliente, Template, LogEnvio, FilaMensagem

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        """Inicializa conexão com PostgreSQL"""
        self.connection_params = {
            'host': os.getenv('PGHOST', 'localhost'),
            'database': os.getenv('PGDATABASE', 'bot_clientes'),
            'user': os.getenv('PGUSER', 'postgres'),
            'password': os.getenv('PGPASSWORD', ''),
            'port': os.getenv('PGPORT', '5432')
        }
        
        # Cache para consultas frequentes
        self._cache = {}
        self._cache_ttl = {}
        self._cache_timeout = 300  # 5 minutos
        
        self.init_database()
    
    def get_connection(self):
        """Cria nova conexão com o banco"""
        try:
            conn = psycopg2.connect(**self.connection_params)
            conn.autocommit = False  # Controle manual de transações
            return conn
        except Exception as e:
            logger.error(f"Erro ao conectar com PostgreSQL: {e}")
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
    
    def init_database(self):
        """Inicializa tabelas do banco de dados"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Criar tabelas
                    self.create_tables(cursor)
                    self.create_indexes(cursor)
                    self.insert_default_templates(cursor)
                    self.insert_default_configs(cursor)
                    conn.commit()
                    logger.info("Banco de dados inicializado com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao inicializar banco: {e}")
            raise
    
    def create_tables(self, cursor):
        """Cria todas as tabelas necessárias"""
        
        # Tabela de clientes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                telefone VARCHAR(20) NOT NULL,
                pacote VARCHAR(255) NOT NULL,
                valor DECIMAL(10,2) NOT NULL,
                servidor VARCHAR(255),
                vencimento DATE NOT NULL,
                ativo BOOLEAN DEFAULT TRUE,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de configurações do sistema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                id SERIAL PRIMARY KEY,
                chave VARCHAR(100) UNIQUE NOT NULL,
                valor TEXT,
                descricao TEXT,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        # Tabela de logs de envio
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs_envio (
                id SERIAL PRIMARY KEY,
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
        
        # Tabela de fila de mensagens
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
        

        
        logger.info("Tabelas criadas com sucesso!")
    
    def create_indexes(self, cursor):
        """Cria índices para otimização"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_clientes_telefone ON clientes(telefone)",
            "CREATE INDEX IF NOT EXISTS idx_clientes_vencimento ON clientes(vencimento)",
            "CREATE INDEX IF NOT EXISTS idx_clientes_ativo ON clientes(ativo)",
            "CREATE INDEX IF NOT EXISTS idx_logs_cliente_id ON logs_envio(cliente_id)",
            "CREATE INDEX IF NOT EXISTS idx_logs_data_envio ON logs_envio(data_envio)",
            "CREATE INDEX IF NOT EXISTS idx_fila_agendado ON fila_mensagens(agendado_para)",
            "CREATE INDEX IF NOT EXISTS idx_fila_processado ON fila_mensagens(processado)",
            "CREATE INDEX IF NOT EXISTS idx_configuracoes_chave ON configuracoes(chave)"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        logger.info("Índices criados com sucesso!")
    
    def insert_default_templates(self, cursor):
        """Insere templates padrão do sistema"""
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
            cursor.execute("""
                INSERT INTO templates (nome, descricao, tipo, conteudo)
                VALUES (%(nome)s, %(descricao)s, %(tipo)s, %(conteudo)s)
                ON CONFLICT (nome) DO NOTHING
            """, template)
        
        logger.info("Templates padrão inseridos com sucesso!")
    
    def insert_default_configs(self, cursor):
        """Insere configurações padrão do sistema"""
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
            cursor.execute("""
                INSERT INTO configuracoes (chave, valor, descricao)
                VALUES (%s, %s, %s)
                ON CONFLICT (chave) DO NOTHING
            """, (chave, valor, descricao))
        
        logger.info("Configurações padrão inseridas com sucesso!")
    
    # === MÉTODOS DE CLIENTES ===
    
    def cadastrar_cliente(self, nome, telefone, pacote, valor, servidor, vencimento, info_adicional=None):
        """Cadastra novo cliente e invalida cache"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO clientes (nome, telefone, pacote, valor, servidor, vencimento, info_adicional)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (nome, telefone, pacote, valor, servidor, vencimento, info_adicional))
                    
                    cliente_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    # Invalidar cache de clientes
                    self.invalidate_cache("clientes")
                    
                    logger.info(f"Cliente cadastrado: ID {cliente_id}, Nome: {nome}")
                    return cliente_id
                    
        except Exception as e:
            logger.error(f"Erro ao cadastrar cliente: {e}")
            raise
    
    def criar_cliente(self, nome, telefone, pacote, valor, servidor, vencimento, info_adicional=None):
        """Alias para cadastrar_cliente (compatibilidade)"""
        return self.cadastrar_cliente(nome, telefone, pacote, valor, servidor, vencimento, info_adicional)
    
    def listar_clientes(self, apenas_ativos=True, limit=None):
        """Lista clientes com informações de vencimento e cache otimizado"""
        cache_key = f"clientes_{apenas_ativos}_{limit}"
        
        # Verificar cache primeiro
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached
        
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where_clause = "WHERE ativo = TRUE" if apenas_ativos else ""
                    limit_clause = f"LIMIT {limit}" if limit else ""
                    
                    cursor.execute(f"""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro, info_adicional,
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
                    """)
                    
                    clientes = cursor.fetchall()
                    result = [dict(cliente) for cliente in clientes]
                    
                    # Cache apenas listas pequenas (< 1000 registros)
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
    
    def buscar_cliente_por_id(self, cliente_id):
        """Busca cliente por ID"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro, data_atualizacao, info_adicional,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE id = %s
                    """, (cliente_id,))
                    
                    cliente = cursor.fetchone()
                    return dict(cliente) if cliente else None
                    
        except Exception as e:
            logger.error(f"Erro ao buscar cliente por ID: {e}")
            raise
    
    def buscar_cliente_por_telefone(self, telefone):
        """Busca cliente por telefone - retorna o primeiro encontrado"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE telefone = %s AND ativo = TRUE
                        ORDER BY data_cadastro DESC
                        LIMIT 1
                    """, (telefone,))
                    
                    cliente = cursor.fetchone()
                    return dict(cliente) if cliente else None
                    
        except Exception as e:
            logger.error(f"Erro ao buscar cliente por telefone: {e}")
            raise
    
    def buscar_clientes_por_telefone(self, telefone):
        """Busca todos os clientes com o mesmo telefone"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE telefone = %s AND ativo = TRUE
                        ORDER BY vencimento ASC
                    """, (telefone,))
                    
                    clientes = cursor.fetchall()
                    return [dict(cliente) for cliente in clientes]
                    
        except Exception as e:
            logger.error(f"Erro ao buscar clientes por telefone: {e}")
            raise
    
    def atualizar_vencimento_cliente(self, cliente_id, novo_vencimento):
        """Atualiza data de vencimento do cliente"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE clientes 
                        SET vencimento = %s, data_atualizacao = CURRENT_TIMESTAMP
                        WHERE id = %s AND ativo = TRUE
                    """, (novo_vencimento, cliente_id))
                    
                    if cursor.rowcount == 0:
                        raise ValueError("Cliente não encontrado ou inativo")
                    
                    conn.commit()
                    logger.info(f"Vencimento atualizado para cliente ID {cliente_id}: {novo_vencimento}")
                    
        except Exception as e:
            logger.error(f"Erro ao atualizar vencimento: {e}")
            raise
    
    def excluir_cliente(self, cliente_id):
        """Exclui cliente definitivamente"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Primeiro, excluir logs relacionados
                    cursor.execute("DELETE FROM logs_envio WHERE cliente_id = %s", (cliente_id,))
                    
                    # Depois, excluir mensagens na fila
                    cursor.execute("DELETE FROM fila_mensagens WHERE cliente_id = %s", (cliente_id,))
                    
                    # Finalmente, excluir o cliente
                    cursor.execute("DELETE FROM clientes WHERE id = %s", (cliente_id,))
                    
                    if cursor.rowcount == 0:
                        raise ValueError("Cliente não encontrado")
                    
                    conn.commit()
                    logger.info(f"Cliente ID {cliente_id} excluído definitivamente")
                    
        except Exception as e:
            logger.error(f"Erro ao excluir cliente: {e}")
            raise
    
    def buscar_clientes(self, termo):
        """Busca clientes por nome ou telefone"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            ativo, data_cadastro,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE (LOWER(nome) LIKE LOWER(%s) OR telefone LIKE %s)
                        AND ativo = TRUE
                        ORDER BY nome ASC
                        LIMIT 20
                    """, (f'%{termo}%', f'%{termo}%'))
                    
                    clientes = cursor.fetchall()
                    return [dict(cliente) for cliente in clientes]
                    
        except Exception as e:
            logger.error(f"Erro ao buscar clientes: {e}")
            raise
    
    def listar_clientes_vencendo(self, dias=3):
        """Lista clientes com vencimento próximo"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT 
                            id, nome, telefone, pacote, valor, servidor, vencimento,
                            (vencimento - CURRENT_DATE) as dias_vencimento
                        FROM clientes 
                        WHERE vencimento <= CURRENT_DATE + INTERVAL '%s days'
                        AND ativo = TRUE
                        ORDER BY vencimento ASC
                    """, (dias,))
                    
                    clientes = cursor.fetchall()
                    return [dict(cliente) for cliente in clientes]
                    
        except Exception as e:
            logger.error(f"Erro ao listar clientes vencendo: {e}")
            raise
    
    def atualizar_cliente(self, cliente_id, **kwargs):
        """Atualiza dados do cliente"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Construir query dinamicamente baseado nos campos fornecidos
                    campos = []
                    valores = []
                    
                    for campo, valor in kwargs.items():
                        if valor is not None:
                            campos.append(f"{campo} = %s")
                            valores.append(valor)
                    
                    if not campos:
                        return False
                    
                    campos.append("data_atualizacao = CURRENT_TIMESTAMP")
                    valores.append(cliente_id)
                    
                    query = f"""
                        UPDATE clientes 
                        SET {', '.join(campos)}
                        WHERE id = %s
                    """
                    
                    cursor.execute(query, valores)
                    conn.commit()
                    
                    return cursor.rowcount > 0
                    
        except Exception as e:
            logger.error(f"Erro ao atualizar cliente: {e}")
            raise
    
    def desativar_cliente(self, cliente_id):
        """Desativa cliente (soft delete)"""
        return self.atualizar_cliente(cliente_id, ativo=False)
    
    def reativar_cliente(self, cliente_id):
        """Reativa cliente"""
        return self.atualizar_cliente(cliente_id, ativo=True)
    
    # === MÉTODOS DE TEMPLATES ===
    
    def listar_templates(self, apenas_ativos=True):
        """Lista todos os templates"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where_clause = "WHERE ativo = TRUE" if apenas_ativos else ""
                    
                    cursor.execute(f"""
                        SELECT id, nome, descricao, conteudo, tipo, ativo, uso_count,
                               data_criacao, data_atualizacao
                        FROM templates 
                        {where_clause}
                        ORDER BY nome ASC
                    """)
                    
                    templates = cursor.fetchall()
                    return [dict(template) for template in templates]
                    
        except Exception as e:
            logger.error(f"Erro ao listar templates: {e}")
            raise
    
    def obter_template(self, template_id):
        """Obtém template por ID"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, nome, descricao, conteudo, tipo, ativo, uso_count
                        FROM templates 
                        WHERE id = %s
                    """, (template_id,))
                    
                    template = cursor.fetchone()
                    return dict(template) if template else None
                    
        except Exception as e:
            logger.error(f"Erro ao obter template: {e}")
            raise
    
    def obter_template_por_tipo(self, tipo):
        """Obtém template por tipo"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, nome, descricao, conteudo, tipo, ativo, uso_count
                        FROM templates 
                        WHERE tipo = %s AND ativo = TRUE
                        LIMIT 1
                    """, (tipo,))
                    
                    template = cursor.fetchone()
                    return dict(template) if template else None
                    
        except Exception as e:
            logger.error(f"Erro ao obter template por tipo: {e}")
            raise
    
    def buscar_template_por_id(self, template_id):
        """Busca template por ID (alias para compatibilidade)"""
        return self.obter_template(template_id)
    
    def excluir_template(self, template_id):
        """Exclui template definitivamente"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Primeiro, remover logs relacionados
                    cursor.execute("DELETE FROM logs_envio WHERE template_id = %s", (template_id,))
                    
                    # Depois, remover da fila de mensagens
                    cursor.execute("DELETE FROM fila_mensagens WHERE template_id = %s", (template_id,))
                    
                    # Finalmente, excluir o template
                    cursor.execute("DELETE FROM templates WHERE id = %s", (template_id,))
                    
                    if cursor.rowcount == 0:
                        raise ValueError("Template não encontrado")
                    
                    conn.commit()
                    logger.info(f"Template ID {template_id} excluído definitivamente")
                    
        except Exception as e:
            logger.error(f"Erro ao excluir template: {e}")
            raise
    
    def criar_template(self, nome, descricao, conteudo, tipo='geral'):
        """Cria novo template"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO templates (nome, descricao, conteudo, tipo)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (nome, descricao, conteudo, tipo))
                    
                    template_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    logger.info(f"Template criado: ID {template_id}, Nome: {nome}")
                    return template_id
                    
        except Exception as e:
            logger.error(f"Erro ao criar template: {e}")
            raise
    
    def atualizar_template(self, template_id, nome=None, descricao=None, conteudo=None):
        """Atualiza template"""
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
                    valores.append(template_id)
                    
                    query = f"""
                        UPDATE templates 
                        SET {', '.join(campos)}
                        WHERE id = %s
                    """
                    
                    cursor.execute(query, valores)
                    conn.commit()
                    
                    return cursor.rowcount > 0
                    
        except Exception as e:
            logger.error(f"Erro ao atualizar template: {e}")
            raise
    
    def atualizar_template_campo(self, template_id, campo, valor):
        """Atualiza campo específico do template"""
        try:
            campos_validos = ['nome', 'descricao', 'conteudo', 'tipo', 'ativo']
            if campo not in campos_validos:
                raise ValueError(f"Campo '{campo}' não é válido. Use: {', '.join(campos_validos)}")
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = f"""
                        UPDATE templates 
                        SET {campo} = %s, data_atualizacao = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """
                    
                    cursor.execute(query, (valor, template_id))
                    conn.commit()
                    
                    if cursor.rowcount == 0:
                        logger.warning(f"Template ID {template_id} não encontrado para atualização")
                        return False
                    
                    logger.info(f"Template ID {template_id} - campo '{campo}' atualizado")
                    return True
                    
        except Exception as e:
            logger.error(f"Erro ao atualizar campo do template: {e}")
            raise
    
    def incrementar_uso_template(self, template_id):
        """Incrementa contador de uso do template"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE templates 
                        SET uso_count = uso_count + 1
                        WHERE id = %s
                    """, (template_id,))
                    conn.commit()
                    
        except Exception as e:
            logger.error(f"Erro ao incrementar uso do template: {e}")
    
    # === MÉTODOS DE LOGS ===
    
    def registrar_envio(self, cliente_id, template_id, telefone, mensagem, tipo_envio, sucesso, erro=None, message_id=None):
        """Registra log de envio de mensagem"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO logs_envio 
                        (cliente_id, template_id, telefone, mensagem, tipo_envio, sucesso, erro, message_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (cliente_id, template_id, telefone, mensagem, tipo_envio, sucesso, erro, message_id))
                    
                    log_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    # Incrementar contador do template se enviado com sucesso
                    if sucesso and template_id:
                        self.incrementar_uso_template(template_id)
                    
                    return log_id
                    
        except Exception as e:
            logger.error(f"Erro ao registrar envio: {e}")
            raise
    
    def registrar_envio_manual(self, cliente_id, template_id, mensagem):
        """Registra envio manual"""
        cliente = self.buscar_cliente_por_id(cliente_id)
        return self.registrar_envio(
            cliente_id=cliente_id,
            template_id=template_id,
            telefone=cliente['telefone'],
            mensagem=mensagem,
            tipo_envio='manual',
            sucesso=True
        )
    
    def obter_logs_envios(self, cliente_id=None, limit=50):
        """Obtém logs de envios"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where_clause = "WHERE l.cliente_id = %s" if cliente_id else ""
                    params = [cliente_id] if cliente_id else []
                    
                    if limit:
                        params.append(limit)
                    
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
                        {'LIMIT %s' if limit else ''}
                    """, params)
                    
                    logs = cursor.fetchall()
                    return [dict(log) for log in logs]
                    
        except Exception as e:
            logger.error(f"Erro ao obter logs: {e}")
            raise
    
    # === MÉTODOS DE FILA DE MENSAGENS ===
    
    def adicionar_fila_mensagem(self, cliente_id, template_id, telefone, mensagem, tipo_mensagem, agendado_para):
        """Adiciona mensagem na fila de envio"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO fila_mensagens 
                        (cliente_id, template_id, telefone, mensagem, tipo_mensagem, agendado_para)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (cliente_id, template_id, telefone, mensagem, tipo_mensagem, agendado_para))
                    
                    fila_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    logger.info(f"Mensagem adicionada à fila: ID {fila_id}")
                    return fila_id
                    
        except Exception as e:
            logger.error(f"Erro ao adicionar mensagem na fila: {e}")
            raise
    
    def obter_mensagens_pendentes(self, limit=100):
        """Obtém mensagens pendentes para envio"""
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
                        WHERE f.processado = FALSE 
                        AND f.agendado_para <= CURRENT_TIMESTAMP
                        AND f.tentativas < f.max_tentativas
                        ORDER BY f.agendado_para ASC
                        LIMIT %s
                    """, (limit,))
                    
                    mensagens = cursor.fetchall()
                    return [dict(msg) for msg in mensagens]
                    
        except Exception as e:
            logger.error(f"Erro ao obter mensagens pendentes: {e}")
            raise
    
    def marcar_mensagem_processada(self, fila_id, sucesso, erro=None):
        """Marca mensagem como processada"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    if sucesso:
                        cursor.execute("""
                            UPDATE fila_mensagens 
                            SET processado = TRUE, data_processamento = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (fila_id,))
                    else:
                        cursor.execute("""
                            UPDATE fila_mensagens 
                            SET tentativas = tentativas + 1
                            WHERE id = %s
                        """, (fila_id,))
                    
                    conn.commit()
                    
        except Exception as e:
            logger.error(f"Erro ao marcar mensagem processada: {e}")
            raise
    
    def limpar_fila_processadas(self, dias=7):
        """Remove mensagens processadas antigas da fila"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM fila_mensagens 
                        WHERE processado = TRUE 
                        AND data_processamento < CURRENT_TIMESTAMP - INTERVAL '%s days'
                    """, (dias,))
                    
                    removidas = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"Removidas {removidas} mensagens antigas da fila")
                    return removidas
                    
        except Exception as e:
            logger.error(f"Erro ao limpar fila: {e}")
            raise
    
    def limpar_mensagens_futuras(self):
        """Remove mensagens agendadas para envio futuro (mais de 1 dia)"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM fila_mensagens 
                        WHERE processado = FALSE 
                        AND agendado_para > CURRENT_TIMESTAMP + INTERVAL '1 day'
                    """)
                    
                    removidas = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"Removidas {removidas} mensagens agendadas para futuro distante")
                    return removidas
                    
        except Exception as e:
            logger.error(f"Erro ao limpar mensagens futuras: {e}")
            raise
    
    # === MÉTODOS DE ESTATÍSTICAS ===
    
    def obter_estatisticas(self):
        """Obtém estatísticas gerais do sistema"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    stats = {}
                    
                    # Total de clientes ativos
                    cursor.execute("SELECT COUNT(*) FROM clientes WHERE ativo = TRUE")
                    stats['total_clientes'] = cursor.fetchone()[0]
                    
                    # Novos clientes este mês
                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE 
                        AND data_cadastro >= date_trunc('month', CURRENT_DATE)
                    """)
                    stats['novos_mes'] = cursor.fetchone()[0]
                    
                    # Receita mensal
                    cursor.execute("""
                        SELECT COALESCE(SUM(valor), 0) FROM clientes 
                        WHERE ativo = TRUE
                    """)
                    stats['receita_mensal'] = float(cursor.fetchone()[0])
                    stats['receita_anual'] = stats['receita_mensal'] * 12
                    
                    # Vencimentos
                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE AND vencimento < CURRENT_DATE
                    """)
                    stats['vencidos'] = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE AND vencimento = CURRENT_DATE
                    """)
                    stats['vencem_hoje'] = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE 
                        AND vencimento BETWEEN CURRENT_DATE + INTERVAL '1 day' 
                        AND CURRENT_DATE + INTERVAL '3 days'
                    """)
                    stats['vencem_3dias'] = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        SELECT COUNT(*) FROM clientes 
                        WHERE ativo = TRUE 
                        AND vencimento BETWEEN CURRENT_DATE 
                        AND CURRENT_DATE + INTERVAL '7 days'
                    """)
                    stats['vencem_semana'] = cursor.fetchone()[0]
                    
                    # Mensagens hoje
                    cursor.execute("""
                        SELECT COUNT(*) FROM logs_envio 
                        WHERE DATE(data_envio) = CURRENT_DATE
                    """)
                    stats['mensagens_hoje'] = cursor.fetchone()[0]
                    
                    # Fila de mensagens
                    cursor.execute("""
                        SELECT COUNT(*) FROM fila_mensagens 
                        WHERE processado = FALSE
                    """)
                    stats['fila_mensagens'] = cursor.fetchone()[0]
                    
                    # Templates
                    cursor.execute("SELECT COUNT(*) FROM templates WHERE ativo = TRUE")
                    stats['total_templates'] = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        SELECT nome FROM templates 
                        WHERE ativo = TRUE 
                        ORDER BY uso_count DESC 
                        LIMIT 1
                    """)
                    resultado = cursor.fetchone()
                    stats['template_mais_usado'] = resultado[0] if resultado else 'Nenhum'
                    
                    return stats
                    
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            raise
    
    # === MÉTODOS DE CONFIGURAÇÃO ===
    
    def obter_configuracao(self, chave, valor_padrao=None):
        """Obtém valor de configuração"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT valor FROM configuracoes WHERE chave = %s
                    """, (chave,))
                    
                    resultado = cursor.fetchone()
                    return resultado[0] if resultado else valor_padrao
                    
        except Exception as e:
            logger.error(f"Erro ao obter configuração: {e}")
            return valor_padrao
    
    def salvar_configuracao(self, chave, valor, descricao=None):
        """Salva configuração"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO configuracoes (chave, valor, descricao)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (chave) 
                        DO UPDATE SET 
                            valor = EXCLUDED.valor,
                            descricao = COALESCE(EXCLUDED.descricao, configuracoes.descricao),
                            data_atualizacao = CURRENT_TIMESTAMP
                    """, (chave, valor, descricao))
                    
                    conn.commit()
                    
        except Exception as e:
            logger.error(f"Erro ao salvar configuração: {e}")
            raise
    
    def cancelar_mensagem_fila(self, mensagem_id):
        """Cancela uma mensagem agendada da fila"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM fila_mensagens 
                        WHERE id = %s AND processado = FALSE
                        RETURNING cliente_id, tipo_mensagem
                    """, (mensagem_id,))
                    
                    resultado = cursor.fetchone()
                    if not resultado:
                        return False
                    
                    conn.commit()
                    logger.info(f"Mensagem ID {mensagem_id} cancelada da fila")
                    return True
                    
        except Exception as e:
            logger.error(f"Erro ao cancelar mensagem da fila: {e}")
            raise
    
    def obter_todas_mensagens_fila(self, limit=50):
        """Obtém todas as mensagens da fila (pendentes e futuras)"""
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
                        WHERE f.processado = FALSE
                        ORDER BY f.agendado_para ASC
                        LIMIT %s
                    """, (limit,))
                    
                    mensagens = cursor.fetchall()
                    return [dict(msg) for msg in mensagens]
                    
        except Exception as e:
            logger.error(f"Erro ao obter mensagens da fila: {e}")
            raise
    
    def buscar_mensagens_fila_cliente(self, cliente_id, apenas_pendentes=True):
        """Busca mensagens na fila de um cliente específico"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    query = """
                        SELECT 
                            f.id, f.cliente_id, f.template_id, f.telefone, f.mensagem,
                            f.tipo_mensagem, f.agendado_para, f.tentativas, f.max_tentativas,
                            f.processado, f.data_criacao,
                            c.nome as cliente_nome, c.pacote
                        FROM fila_mensagens f
                        LEFT JOIN clientes c ON f.cliente_id = c.id
                        WHERE f.cliente_id = %s
                    """
                    
                    params = [cliente_id]
                    
                    if apenas_pendentes:
                        query += " AND f.processado = FALSE"
                    
                    query += " ORDER BY f.agendado_para ASC"
                    
                    cursor.execute(query, params)
                    mensagens = cursor.fetchall()
                    return [dict(msg) for msg in mensagens]
                    
        except Exception as e:
            logger.error(f"Erro ao buscar mensagens da fila do cliente {cliente_id}: {e}")
            raise

    def verificar_mensagem_existente(self, cliente_id, tipo_mensagem, data_envio):
        """Verifica se já existe uma mensagem agendada para o cliente na data especificada"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id FROM fila_mensagens 
                        WHERE cliente_id = %s 
                        AND tipo_mensagem = %s 
                        AND DATE(agendado_para) = %s 
                        AND processado = FALSE
                        LIMIT 1
                    """, (cliente_id, tipo_mensagem, data_envio))
                    
                    resultado = cursor.fetchone()
                    return resultado is not None
                    
        except Exception as e:
            logger.error(f"Erro ao verificar mensagem existente: {e}")
            return False

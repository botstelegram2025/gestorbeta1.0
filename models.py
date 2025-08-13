"""
Modelos de dados para o sistema de gestão de clientes
Define as estruturas de dados utilizadas no banco PostgreSQL
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

@dataclass
class Cliente:
    """Modelo de dados para clientes"""
    id: Optional[int] = None
    nome: str = ""
    telefone: str = ""
    pacote: str = ""
    valor: float = 0.0
    servidor: str = ""
    vencimento: Optional[date] = None
    ativo: bool = True
    data_cadastro: Optional[datetime] = None
    data_atualizacao: Optional[datetime] = None
    dias_vencimento: Optional[int] = None
    status_vencimento: Optional[str] = None

@dataclass
class Template:
    """Modelo de dados para templates de mensagens"""
    id: Optional[int] = None
    nome: str = ""
    descricao: str = ""
    conteudo: str = ""
    tipo: str = "geral"
    ativo: bool = True
    uso_count: int = 0
    data_criacao: Optional[datetime] = None
    data_atualizacao: Optional[datetime] = None

@dataclass
class LogEnvio:
    """Modelo de dados para logs de envio"""
    id: Optional[int] = None
    cliente_id: Optional[int] = None
    template_id: Optional[int] = None
    telefone: str = ""
    mensagem: str = ""
    tipo_envio: str = ""
    sucesso: bool = False
    erro: Optional[str] = None
    message_id: Optional[str] = None
    data_envio: Optional[datetime] = None
    cliente_nome: Optional[str] = None
    template_nome: Optional[str] = None

@dataclass
class FilaMensagem:
    """Modelo de dados para fila de mensagens"""
    id: Optional[int] = None
    cliente_id: Optional[int] = None
    template_id: Optional[int] = None
    telefone: str = ""
    mensagem: str = ""
    tipo_mensagem: str = ""
    agendado_para: Optional[datetime] = None
    processado: bool = False
    tentativas: int = 0
    max_tentativas: int = 3
    data_criacao: Optional[datetime] = None
    data_processamento: Optional[datetime] = None
    cliente_nome: Optional[str] = None

@dataclass
class Configuracao:
    """Modelo de dados para configurações do sistema"""
    id: Optional[int] = None
    chave: str = ""
    valor: str = ""
    descricao: Optional[str] = None
    data_atualizacao: Optional[datetime] = None

# Tipos de templates predefinidos
TIPOS_TEMPLATE = {
    'vencimento_2dias': 'Aviso 2 dias antes do vencimento',
    'vencimento_hoje': 'Aviso no dia do vencimento',
    'vencimento_1dia_apos': 'Aviso 1 dia após vencimento',
    'boas_vindas': 'Mensagem de boas vindas',
    'cobranca_manual': 'Cobrança manual',
    'geral': 'Template geral'
}

# Status de vencimento
STATUS_VENCIMENTO = {
    'em_dia': '🟢 Em dia',
    'vence_em_breve': '🟡 Vence em breve',
    'vence_hoje': '🟠 Vence hoje',
    'vencido': '🔴 Vencido'
}

# Tipos de envio
TIPOS_ENVIO = {
    'automatico': 'Envio automático',
    'manual': 'Envio manual',
    'agendado': 'Envio agendado',
    'teste': 'Envio de teste'
}

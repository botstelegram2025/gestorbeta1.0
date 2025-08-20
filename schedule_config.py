"""
Configurações de Horários do Sistema
Integração com o Scheduler (compatível com worker minutal e verificação 05:00)
"""

import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# ===== Chaves de configuração (com aliases p/ retrocompatibilidade) =====
CHAVE_ENVIO_CANONICA = 'horario_envio'
CHAVE_ENVIO_LEGADA   = 'horario_envio_diario'

CHAVE_VERIF_CANONICA = 'horario_verificacao'
CHAVE_VERIF_LEGADA   = 'horario_verificacao_diaria'

CHAVE_LIMPEZA_CANONICA = 'horario_limpeza'
CHAVE_LIMPEZA_LEGADA   = 'horario_limpeza_fila'

CHAVE_TZ = 'timezone_sistema'

class ScheduleConfig:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.timezone = pytz.timezone('America/Sao_Paulo')

    # ... restante do código (métodos de salvar configs, menus, recriar jobs, etc.)

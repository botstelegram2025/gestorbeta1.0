"""
Módulo de Configuração de Horários
Compatível com scheduler_patched.py (worker minutal + verificação 05:00)
"""

import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# ===== Chaves de configuração (canônicas + legadas p/ compatibilidade) =====
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

    # ---------------- Carregar configs ----------------
    def carregar_horarios(self, chat_id):
        try:
            cursor = self.bot.conn.cursor()
            cursor.execute("""
                SELECT chave, valor FROM configuracoes WHERE chat_id = ?
            """, (chat_id,))
            rows = cursor.fetchall()

            confs = {row[0]: row[1] for row in rows}

            return {
                'envio': confs.get(CHAVE_ENVIO_CANONICA) or confs.get(CHAVE_ENVIO_LEGADA),
                'verificacao': confs.get(CHAVE_VERIF_CANONICA) or confs.get(CHAVE_VERIF_LEGADA),
                'limpeza': confs.get(CHAVE_LIMPEZA_CANONICA) or confs.get(CHAVE_LIMPEZA_LEGADA),
                'tz': confs.get(CHAVE_TZ, 'America/Sao_Paulo')
            }
        except Exception as e:
            logger.error(f"Erro ao carregar horários: {e}")
            return None

    # ---------------- Salvar configs ----------------
    def salvar_horario(self, chat_id, chave, valor):
        try:
            cursor = self.bot.conn.cursor()
            # salva chave canônica
            cursor.execute("""
                INSERT INTO configuracoes (chat_id, chave, valor)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id, chave) DO UPDATE SET valor=excluded.valor
            """, (chat_id, chave, valor))

            # salva também chave legada, se aplicável
            if chave == CHAVE_ENVIO_CANONICA:
                chave_legada = CHAVE_ENVIO_LEGADA
            elif chave == CHAVE_VERIF_CANONICA:
                chave_legada = CHAVE_VERIF_LEGADA
            elif chave == CHAVE_LIMPEZA_CANONICA:
                chave_legada = CHAVE_LIMPEZA_LEGADA
            else:
                chave_legada = None

            if chave_legada:
                cursor.execute("""
                    INSERT INTO configuracoes (chat_id, chave, valor)
                    VALUES (?, ?, ?)
                    ON CONFLICT(chat_id, chave) DO UPDATE SET valor=excluded.valor
                """, (chat_id, chave_legada, valor))

            self.bot.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar horário {chave}: {e}")
            return False

    # ---------------- Reprogramar jobs ----------------
    def _reprogramar_jobs_seguro(self):
        try:
            scheduler = self.bot.scheduler

            # Remove duplicatas por id
            vistos = set()
            for job in list(scheduler.jobs):
                if job.id in vistos:
                    scheduler.remove_job(job.id)
                else:
                    vistos.add(job.id)

            # Garante recriação dos principais jobs
            if hasattr(scheduler, '_setup_main_jobs'):
                scheduler._setup_main_jobs()

            if not scheduler.running:
                scheduler.start()

            logger.info("Jobs reprogramados com sucesso.")
        except Exception as e:
            logger.error(f"Falha ao reprogramar jobs: {e}")

    def recriar_jobs(self):
        self._reprogramar_jobs_seguro()

    def resetar_horarios_padrao(self, chat_id):
        try:
            self.salvar_horario(chat_id, CHAVE_ENVIO_CANONICA, '09:00')
            self.salvar_horario(chat_id, CHAVE_VERIF_CANONICA, '05:00')
            self.salvar_horario(chat_id, CHAVE_LIMPEZA_CANONICA, '23:59')
            self.salvar_horario(chat_id, CHAVE_TZ, 'America/Sao_Paulo')
            self._reprogramar_jobs_seguro()
            return True
        except Exception as e:
            logger.error(f"Erro ao resetar horários: {e}")
            return False

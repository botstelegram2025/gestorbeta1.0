"""
Configurações de Horários do Sistema
Compatível com o scheduler (worker minutal + verificação 05:00)
e com DB via self.bot.db.get_connection() e coluna chat_id_usuario.
"""

import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# Chaves canônicas + legadas (retrocompatibilidade)
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

    # ===================== Helpers de persistência =====================
    def _buscar_configs_usuario(self, chat_id):
        """
        Lê TODAS as configs do usuário e resolve:
        - horario_envio (canônica ou legada)
        - horario_verificacao (canônica ou legada)
        - horario_limpeza (canônica ou legada)
        - timezone_sistema (opcional)
        """
        cfg = {
            'horario_envio': '09:00',
            'horario_verificacao': '09:00',
            'horario_limpeza': '02:00',
            'timezone_sistema': 'America/Sao_Paulo'
        }
        try:
            if not getattr(self.bot, 'db', None):
                return cfg

            with self.bot.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT chave, valor
                          FROM configuracoes
                         WHERE chat_id_usuario = %s
                    """, (chat_id,))
                    for chave, valor in cursor.fetchall():
                        if chave in (CHAVE_ENVIO_CANONICA, CHAVE_ENVIO_LEGADA):
                            cfg['horario_envio'] = valor
                        elif chave in (CHAVE_VERIF_CANONICA, CHAVE_VERIF_LEGADA):
                            cfg['horario_verificacao'] = valor
                        elif chave in (CHAVE_LIMPEZA_CANONICA, CHAVE_LIMPEZA_LEGADA):
                            cfg['horario_limpeza'] = valor
                        elif chave == CHAVE_TZ:
                            cfg['timezone_sistema'] = valor
        except Exception as e:
            logger.warning(f'Falha ao buscar configs de {chat_id}: {e}')
        return cfg

    def _salvar_config(self, chat_id, chave_canonica, valor):
        """
        Salva isolado por usuário e mantém a chave legada em sincronia.
        """
        if not getattr(self.bot, 'db', None):
            raise RuntimeError('DB não disponível')

        # Mapear chave legada correspondente
        chave_legada = None
        if chave_canonica == CHAVE_ENVIO_CANONICA:
            chave_legada = CHAVE_ENVIO_LEGADA
        elif chave_canonica == CHAVE_VERIF_CANONICA:
            chave_legada = CHAVE_VERIF_LEGADA
        elif chave_canonica == CHAVE_LIMPEZA_CANONICA:
            chave_legada = CHAVE_LIMPEZA_LEGADA

        with self.bot.db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Apaga e grava canônica
                cursor.execute("""
                    DELETE FROM configuracoes
                     WHERE chave = %s AND chat_id_usuario = %s
                """, (chave_canonica, chat_id))
                cursor.execute("""
                    INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                    VALUES (%s, %s, %s, %s)
                """, (chave_canonica, valor, 'Horário personalizado do usuário', chat_id))

                # Apaga e grava legada (se houver)
                if chave_legada:
                    cursor.execute("""
                        DELETE FROM configuracoes
                         WHERE chave = %s AND chat_id_usuario = %s
                    """, (chave_legada, chat_id))
                    cursor.execute("""
                        INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                        VALUES (%s, %s, %s, %s)
                    """, (chave_legada, valor, 'Horário (legado) sincronizado', chat_id))
            conn.commit()

    # ===================== Integração com o Scheduler =====================
    def _reprogramar_jobs_seguro(self):
        """
        Reinstala/garante os jobs principais S/ trocar instância da APScheduler.
        - Remove duplicatas por ID
        - Chama self.bot.scheduler._setup_main_jobs()
        - Garante .start() se não estiver rodando
        """
        try:
            sched_wrapper = getattr(self.bot, 'scheduler', None)
            if not sched_wrapper:
                logger.warning('Scheduler wrapper ausente.')
                return False
            sched = getattr(sched_wrapper, 'scheduler', None)
            if sched is None:
                logger.warning('Instância APScheduler ausente.')
                return False

            # Remover duplicatas
            vistos = set()
            for job in list(sched.get_jobs()):
                if job.id in vistos:
                    try:
                        sched.remove_job(job.id)
                    except Exception as e:
                        logger.warning(f'Não removeu duplicata {job.id}: {e}')
                else:
                    vistos.add(job.id)

            # Recriar/garantir jobs oficiais
            if hasattr(sched_wrapper, '_setup_main_jobs'):
                sched_wrapper._setup_main_jobs()
            else:
                logger.warning('scheduler wrapper sem _setup_main_jobs()')

            # Garantir que está rodando
            try:
                if not getattr(sched_wrapper, 'running', False):
                    sched_wrapper.start()
            except Exception as e:
                logger.warning(f'Falha ao iniciar scheduler: {e}')

            return True
        except Exception as e:
            logger.error(f'Erro ao reprogramar jobs: {e}')
            return False

    # ===================== Menus / UI =====================
    def config_horarios_menu(self, chat_id):
        """Menu principal"""
        try:
            agora = datetime.now(self.timezone)
            cfgs = self._buscar_configs_usuario(chat_id)

            mensagem = f"""⏰ CONFIGURAÇÕES DE HORÁRIOS

📅 Seus Horários Atuais (Brasília):
🕘 Envio Diário: {cfgs['horario_envio']}
   └ Mensagens são processadas pelo worker minutal no horário agendado

🕔 Verificação: {cfgs['horario_verificacao']}  
   └ Sistema verifica vencimentos e adiciona à fila

🕚 Limpeza: {cfgs['horario_limpeza']}
   └ Remove mensagens antigas da fila

🌍 Timezone: {cfgs['timezone_sistema']}
⏱️ Horário atual: {agora.strftime('%H:%M:%S')}

🔧 Escolha o que deseja alterar:"""

            inline_keyboard = [
                [
                    {'text': '🕘 Horário de Envio', 'callback_data': 'edit_horario_envio'},
                    {'text': '🕔 Horário Verificação', 'callback_data': 'edit_horario_verificacao'}
                ],
                [
                    {'text': '🕚 Horário Limpeza', 'callback_data': 'edit_horario_limpeza'},
                    {'text': '⏱️ Padrões de Envio', 'callback_data': 'edit_padroes_envio'}
                ],
                [
                    {'text': '🔄 Recriar Jobs', 'callback_data': 'recriar_jobs'},
                    {'text': '📊 Status Jobs', 'callback_data': 'status_jobs'}
                ],
                [
                    {'text': '🔄 Reset para Padrão', 'callback_data': 'reset_horarios_padrao'}
                ],
                [
                    {'text': '🔙 Voltar', 'callback_data': 'voltar_configs'},
                    {'text': '🏠 Menu Principal', 'callback_data': 'menu_principal'}
                ]
            ]

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})
        except Exception as e:
            logger.error(f"Erro ao mostrar menu de horários: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar configurações de horários.")

    def edit_horario_envio(self, chat_id):
        try:
            horario_atual = self._buscar_configs_usuario(chat_id)['horario_envio']
            mensagem = f"""📤 ALTERAR HORÁRIO DE ENVIO

⏰ Atual: {horario_atual} (Brasília)

Este horário define quando as mensagens serão AGENDADAS para o seu usuário.
O envio acontece pontualmente pelo worker minutal no horário agendado.

💡 Recomendações:
• Se verificação às 18:00 → Envio às 18:10
• Se verificação às 09:00 → Envio às 09:15
• Deixe alguns minutos entre verificação e envio

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            horarios_populares = [
                ['09:00', '09:15', '12:00'],
                ['14:00', '16:00', '17:00'],
                ['17:28', '18:00', '18:10'],
                ['19:00', '20:00', '21:00']
            ]
            for linha_horarios in horarios_populares:
                linha = []
                for h in linha_horarios:
                    linha.append({'text': f'🕐 {h}', 'callback_data': f'set_envio_{h.replace(":", "")}'})
                inline_keyboard.append(linha)
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_envio'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})
        except Exception as e:
            logger.error(f"Erro ao configurar horário de envio: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_verificacao(self, chat_id):
        try:
            horario_atual = self._buscar_configs_usuario(chat_id)['horario_verificacao']
            mensagem = f"""🔔 ALTERAR HORÁRIO DE VERIFICAÇÃO

⏰ Atual: {horario_atual} (Brasília)

• Verifica clientes vencidos
• Agenda mensagens para envio posterior
• Detecta vencimentos para notificação

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            horarios_verificacao = [
                ['06:00', '07:00', '08:00'],
                ['09:00', '12:00', '15:00'],
                ['17:00', '18:00', '19:00'],
                ['20:00', '21:00', '22:00']
            ]
            for linha_horarios in horarios_verificacao:
                linha = []
                for h in linha_horarios:
                    linha.append({'text': f'🕐 {h}', 'callback_data': f'set_verificacao_{h.replace(":", "")}'})
                inline_keyboard.append(linha)
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_verificacao'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})
        except Exception as e:
            logger.error(f"Erro ao configurar horário de verificação: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_limpeza(self, chat_id):
        try:
            horario_atual = self._buscar_configs_usuario(chat_id)['horario_limpeza']
            mensagem = f"""🧹 ALTERAR HORÁRIO DE LIMPEZA

⏰ Atual: {horario_atual} (Brasília)

Remove mensagens antigas da fila que não foram enviadas.
Recomendação: madrugada (menos impacto).

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            horarios = ['01:00', '02:00', '03:00', '04:00', '05:00', '23:00', '00:00']
            for i in range(0, len(horarios), 3):
                linha = []
                for j in range(3):
                    if i + j < len(horarios):
                        h = horarios[i + j]
                        linha.append({'text': h, 'callback_data': f'set_limpeza_{h.replace(":", "")}'})
                inline_keyboard.append(linha)

            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_limpeza'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})
        except Exception as e:
            logger.error(f"Erro ao configurar horário de limpeza: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    # ===================== Setters =====================
    def set_horario_envio(self, chat_id, novo_horario):
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            horario_formatado = f"{hora:02d}:{minuto:02d}"
            self._salvar_config(chat_id, CHAVE_ENVIO_CANONICA, horario_formatado)
            self.bot.send_message(chat_id, f"✅ Horário de envio alterado para {horario_formatado}!")
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de envio: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_verificacao(self, chat_id, novo_horario):
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            horario_formatado = f"{hora:02d}:{minuto:02d}"
            self._salvar_config(chat_id, CHAVE_VERIF_CANONICA, horario_formatado)
            self.bot.send_message(chat_id, f"✅ Horário de verificação alterado para {horario_formatado}!")
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de verificação: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_limpeza(self, chat_id, novo_horario):
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            horario_formatado = f"{hora:02d}:{minuto:02d}"
            self._salvar_config(chat_id, CHAVE_LIMPEZA_CANONICA, horario_formatado)
            self.bot.send_message(chat_id, f"✅ Horário de limpeza alterado para {horario_formatado}!")
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de limpeza: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    # ===================== Admin Ops =====================
    def recriar_jobs(self, chat_id):
        try:
            ok = self._reprogramar_jobs_seguro()
            if ok:
                total = 0
                try:
                    total = len(self.bot.scheduler.scheduler.get_jobs())
                except Exception:
                    pass
                self.bot.send_message(chat_id, f"✅ Scheduler recriado.\n📊 {total} jobs ativos")
            else:
                self.bot.send_message(chat_id, "❌ Não foi possível recriar os jobs agora.")
        except Exception as e:
            logger.error(f"Erro ao recriar jobs: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao recriar jobs: {str(e)}")

    def resetar_horarios_padrao(self, chat_id):
        try:
            # padrões
            self._salvar_config(chat_id, CHAVE_ENVIO_CANONICA,   '09:00')
            self._salvar_config(chat_id, CHAVE_VERIF_CANONICA,   '09:00')
            self._salvar_config(chat_id, CHAVE_LIMPEZA_CANONICA, '02:00')
            if getattr(self.bot, 'db', None):
                self.bot.db.salvar_configuracao(CHAVE_TZ, 'America/Sao_Paulo', chat_id_usuario=chat_id)

            self._reprogramar_jobs_seguro()

            msg = """✅ SEUS HORÁRIOS FORAM RESETADOS!

🕘 Envio Diário: 09:00
🕔 Verificação: 09:00
🕚 Limpeza: 02:00
🌍 Timezone: America/Sao_Paulo

⚡ Status: Jobs recriados automaticamente
🔒 Isolamento: Configurações aplicadas apenas à sua conta"""
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"Erro ao resetar horários padrão: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao resetar horários: {str(e)}")

    def limpar_duplicatas(self, chat_id):
        try:
            sched_wrapper = getattr(self.bot, 'scheduler', None)
            if not sched_wrapper:
                self.bot.send_message(chat_id, "❌ Agendador não disponível.")
                return
            sched = getattr(sched_wrapper, 'scheduler', None)
            if sched is None:
                self.bot.send_message(chat_id, "❌ Instância do agendador não encontrada.")
                return

            vistos, removidos = set(), 0
            for job in list(sched.get_jobs()):
                if job.id in vistos:
                    try:
                        sched.remove_job(job.id)
                        removidos += 1
                    except Exception as e:
                        logger.warning(f'Falha removendo duplicata {job.id}: {e}')
                else:
                    vistos.add(job.id)

            # Garantir jobs oficiais
            if hasattr(sched_wrapper, '_setup_main_jobs'):
                sched_wrapper._setup_main_jobs()

            total = len(sched.get_jobs())
            msg = f"✅ Limpeza concluída!\n📊 Jobs ativos: {total}"
            if removidos:
                msg += f"\n🗑️ Removidas {removidos} duplicatas"
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"Erro ao limpar duplicatas: {e}")
            self.bot.send_message(chat_id, f"❌ Erro na limpeza: {str(e)}")

    def status_jobs(self, chat_id):
        try:
            sched_wrapper = getattr(self.bot, 'scheduler', None)
            if not sched_wrapper or not getattr(sched_wrapper, 'scheduler', None):
                self.bot.send_message(chat_id, "❌ Agendador não disponível.")
                return
            sched = sched_wrapper.scheduler
            jobs = sched.get_jobs()

            mensagem = "📊 STATUS DOS JOBS ATIVOS:\n\n"
            if not jobs:
                mensagem += "❌ Nenhum job ativo encontrado."
            else:
                for job in jobs:
                    try:
                        brasilia = pytz.timezone('America/Sao_Paulo')
                        agora = datetime.now(brasilia)
                        next_run_time = job.trigger.get_next_fire_time(None, agora)
                        if next_run_time:
                            next_run_br = next_run_time.astimezone(brasilia)
                            prox = next_run_br.strftime('%d/%m %H:%M:%S')
                        else:
                            prox = 'N/A'
                    except Exception as e:
                        prox = 'N/A'
                        logger.warning(f"Erro ao calcular próxima execução para {job.id}: {e}")
                    nome = getattr(job, 'name', job.id)
                    mensagem += f"• {nome}\n  ID: {job.id}\n  Próxima execução: {prox}\n\n"

            inline_keyboard = [
                [{'text': '🔄 Recriar Jobs', 'callback_data': 'recriar_jobs'}],
                [{'text': '🧹 Limpar Duplicatas', 'callback_data': 'limpar_duplicatas'}],
                [{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}]
            ]
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})
        except Exception as e:
            logger.error(f"Erro ao mostrar status dos jobs: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar status dos jobs.")

    # ===================== Entradas personalizadas =====================
    def horario_personalizado_envio(self, chat_id):
        try:
            self.bot.conversation_states[chat_id] = 'aguardando_horario_envio'
            self.bot.send_message(
                chat_id,
                "⌨️ HORÁRIO PERSONALIZADO - ENVIO\n\n"
                "Digite no formato HH:MM (ex.: 08:30, 14:15, 19:45)",
                reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]}
            )
        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado (envio): {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def horario_personalizado_verificacao(self, chat_id):
        try:
            self.bot.conversation_states[chat_id] = 'aguardando_horario_verificacao'
            self.bot.send_message(
                chat_id,
                "⌨️ HORÁRIO PERSONALIZADO - VERIFICAÇÃO\n\n"
                "Digite no formato HH:MM (ex.: 05:30, 07:00, 09:15)",
                reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]}
            )
        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado (verificação): {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def horario_personalizado_limpeza(self, chat_id):
        try:
            self.bot.conversation_states[chat_id] = 'aguardando_horario_limpeza'
            self.bot.send_message(
                chat_id,
                "⌨️ HORÁRIO PERSONALIZADO - LIMPEZA\n\n"
                "Digite no formato HH:MM (ex.: 01:00, 23:30, 03:15)\n"
                "Sugestão: madrugada para menor impacto.",
                reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]}
            )
        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado (limpeza): {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def processar_horario_personalizado(self, chat_id, texto, estado=None):
        try:
            import re
            if not re.match(r'^([0-1][0-9]|2[0-3]):([0-5][0-9])$', texto or ''):
                self.bot.send_message(chat_id, "❌ Formato inválido! Use HH:MM (ex.: 09:30)")
                return False

            estado = estado or self.bot.conversation_states.get(chat_id)
            hhmm = texto.replace(':', '')
            if estado == 'aguardando_horario_envio':
                self.set_horario_envio(chat_id, hhmm)
            elif estado == 'aguardando_horario_verificacao':
                self.set_horario_verificacao(chat_id, hhmm)
            elif estado == 'aguardando_horario_limpeza':
                self.set_horario_limpeza(chat_id, hhmm)
            else:
                self.bot.send_message(chat_id, "❌ Estado de configuração inválido.")
                return False

            # limpar estado
            self.bot.conversation_states.pop(chat_id, None)
            return True
        except Exception as e:
            logger.error(f"Erro ao processar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao processar horário.")
            return False

    def _get_next_run_time(self, job_id):
        """Obtém próximo horário de execução de um job (best effort)."""
        try:
            sched_wrapper = getattr(self.bot, 'scheduler', None)
            if not sched_wrapper or not getattr(sched_wrapper, 'scheduler', None):
                return "Não agendado"
            job = sched_wrapper.scheduler.get_job(job_id)
            if job and job.next_run_time:
                try:
                    from utils import formatar_datetime_br
                    return formatar_datetime_br(job.next_run_time)
                except Exception:
                    brasilia = pytz.timezone('America/Sao_Paulo')
                    return job.next_run_time.astimezone(brasilia).strftime('%d/%m/%Y %H:%M:%S')
            return "Não agendado"
        except Exception:
            return "Erro ao obter horário"

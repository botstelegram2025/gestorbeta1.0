"""
Configurações de Horários do Sistema
- Persistência via self.bot.db.get_connection() e coluna chat_id_usuario
- Menus com inline keyboard + entradas personalizadas (HH:MM)
- Aliases de compatibilidade: config_horarios / menu_horarios / horarios
- Reprogramação segura dos jobs: chama self.bot.scheduler._setup_main_jobs()
"""

import logging
import re
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
    def __init__(self, bot):
        self.bot = bot
        self.timezone = pytz.timezone('America/Sao_Paulo')

    # ---- Aliases de compatibilidade ----
    def config_horarios(self, chat_id):  # handlers antigos
        return self.config_horarios_menu(chat_id)

    def menu_horarios(self, chat_id):
        return self.config_horarios_menu(chat_id)

    def horarios(self, chat_id):
        return self.config_horarios_menu(chat_id)
    # ------------------------------------

    # ===================== Persistência (DB) =====================
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

        # Mapeia chave legada
        chave_legada = None
        if chave_canonica == CHAVE_ENVIO_CANONICA:
            chave_legada = CHAVE_ENVIO_LEGADA
        elif chave_canonica == CHAVE_VERIF_CANONICA:
            chave_legada = CHAVE_VERIF_LEGADA
        elif chave_canonica == CHAVE_LIMPEZA_CANONICA:
            chave_legada = CHAVE_LIMPEZA_LEGADA

        with self.bot.db.get_connection() as conn:
            with conn.cursor() as cursor:
                # canônica
                cursor.execute("""
                    DELETE FROM configuracoes
                     WHERE chave = %s AND chat_id_usuario = %s
                """, (chave_canonica, chat_id))
                cursor.execute("""
                    INSERT INTO configuracoes (chave, valor, descricao, chat_id_usuario)
                    VALUES (%s, %s, %s, %s)
                """, (chave_canonica, valor, 'Horário personalizado do usuário', chat_id))

                # legada (se houver)
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
        Reinstala/garante os jobs principais S/ trocar a instância da APScheduler.
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

    # ===================== Telas / UI =====================
    def config_horarios_menu(self, chat_id):
        """Menu principal"""
        try:
            agora = datetime.now(self.timezone)
            cfgs = self._buscar_configs_usuario(chat_id)

            mensagem = f"""⚙️ *Configurações de Horários*

📤 Envio: {cfgs['horario_envio']}
🔎 Verificação: {cfgs['horario_verificacao']}
🧹 Limpeza: {cfgs['horario_limpeza']}

🕒 Agora: {agora.strftime('%H:%M:%S')}
Selecione o que deseja alterar:"""

            inline_keyboard = [
                [
                    {'text': '🕘 Horário de Envio', 'callback_data': 'edit_horario_envio'},
                    {'text': '🕔 Horário Verificação', 'callback_data': 'edit_horario_verificacao'}
                ],
                [
                    {'text': '🕚 Horário Limpeza', 'callback_data': 'edit_horario_limpeza'}
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
            self.bot.send_message(chat_id, mensagem, parse_mode="Markdown", reply_markup={'inline_keyboard': inline_keyboard})
        except Exception as e:
            logger.error(f"Erro ao mostrar menu de horários: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar configurações de horários.")

    def edit_horario_envio(self, chat_id):
        try:
            atual = self._buscar_configs_usuario(chat_id)['horario_envio']
            mensagem = f"""📤 *ALTERAR HORÁRIO DE ENVIO*

⏰ Atual: `{atual}`

Escolha uma opção ou informe um *personalizado*:"""
            populares = [
                ['09:00', '09:15', '12:00'],
                ['14:00', '16:00', '17:00'],
                ['17:28', '18:00', '18:10'],
                ['19:00', '20:00', '21:00']
            ]
            kb = {'inline_keyboard': []}
            for linha in populares:
                row = [{'text': f'🕐 {h}', 'callback_data': f'set_envio_{h.replace(":","")}'}
                       for h in linha]
                kb['inline_keyboard'].append(row)
            kb['inline_keyboard'].append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_envio'}])
            kb['inline_keyboard'].append([{'text': '🔙 Voltar', 'callback_data': 'config_horarios'}])
            self.bot.send_message(chat_id, mensagem, parse_mode='Markdown', reply_markup=kb)
        except Exception as e:
            logger.error(f"Erro ao configurar horário de envio: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_verificacao(self, chat_id):
        try:
            atual = self._buscar_configs_usuario(chat_id)['horario_verificacao']
            mensagem = f"""🔔 *ALTERAR HORÁRIO DE VERIFICAÇÃO*

⏰ Atual: `{atual}`

Escolha uma opção ou informe um *personalizado*:"""
            opcoes = [
                ['06:00', '07:00', '08:00'],
                ['09:00', '12:00', '15:00'],
                ['17:00', '18:00', '19:00'],
                ['20:00', '21:00', '22:00']
            ]
            kb = {'inline_keyboard': []}
            for linha in opcoes:
                row = [{'text': f'🕐 {h}', 'callback_data': f'set_verificacao_{h.replace(":","")}'}
                       for h in linha]
                kb['inline_keyboard'].append(row)
            kb['inline_keyboard'].append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_verificacao'}])
            kb['inline_keyboard'].append([{'text': '🔙 Voltar', 'callback_data': 'config_horarios'}])
            self.bot.send_message(chat_id, mensagem, parse_mode='Markdown', reply_markup=kb)
        except Exception as e:
            logger.error(f"Erro ao configurar horário de verificação: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_limpeza(self, chat_id):
        try:
            atual = self._buscar_configs_usuario(chat_id)['horario_limpeza']
            mensagem = f"""🧹 *ALTERAR HORÁRIO DE LIMPEZA*

⏰ Atual: `{atual}`

Escolha uma opção ou informe um *personalizado*:"""
            horarios = ['01:00', '02:00', '03:00', '04:00', '05:00', '23:00', '00:00']
            kb = {'inline_keyboard': []}
            for i in range(0, len(horarios), 3):
                row = []
                for j in range(3):
                    if i + j < len(horarios):
                        h = horarios[i + j]
                        row.append({'text': h, 'callback_data': f'set_limpeza_{h.replace(":","")}'})
                kb['inline_keyboard'].append(row)
            kb['inline_keyboard'].append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_limpeza'}])
            kb['inline_keyboard'].append([{'text': '🔙 Voltar', 'callback_data': 'config_horarios'}])
            self.bot.send_message(chat_id, mensagem, parse_mode='Markdown', reply_markup=kb)
        except Exception as e:
            logger.error(f"Erro ao configurar horário de limpeza: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    # ===================== Setters =====================
    def set_horario_envio(self, chat_id, novo_hhmm_digits):
        try:
            hh, mm = int(novo_hhmm_digits[:2]), int(novo_hhmm_digits[2:])
            valor = f"{hh:02d}:{mm:02d}"
            self._salvar_config(chat_id, CHAVE_ENVIO_CANONICA, valor)
            self.bot.send_message(chat_id, f"✅ Horário de *envio* alterado para `{valor}`", parse_mode='Markdown')
            
            # Processar imediatamente todos os clientes vencidos deste usuário
            enviadas = 0
            if hasattr(self.bot, 'scheduler') and hasattr(self.bot.scheduler, 'processar_todos_vencidos'):
                try:
                    enviadas = self.bot.scheduler.processar_todos_vencidos(chat_id_usuario=chat_id, forcar_reprocesso=False)
                except Exception as e:
                    logger.error(f"Erro ao processar vencidos após alterar horário de envio: {e}")
            
            # Mostrar feedback de quantas mensagens foram enviadas
            if enviadas > 0:
                self.bot.send_message(chat_id, f"📧 {enviadas} mensagens enviadas para clientes vencidos", parse_mode='Markdown')
            else:
                self.bot.send_message(chat_id, "✅ Nenhum cliente vencido para processar no momento", parse_mode='Markdown')
            
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de envio: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_verificacao(self, chat_id, novo_hhmm_digits):
        try:
            hh, mm = int(novo_hhmm_digits[:2]), int(novo_hhmm_digits[2:])
            valor = f"{hh:02d}:{mm:02d}"
            self._salvar_config(chat_id, CHAVE_VERIF_CANONICA, valor)
            self.bot.send_message(chat_id, f"✅ Horário de *verificação* alterado para `{valor}`", parse_mode='Markdown')
            
            # Processar imediatamente todos os clientes vencidos deste usuário
            enviadas = 0
            if hasattr(self.bot, 'scheduler') and hasattr(self.bot.scheduler, 'processar_todos_vencidos'):
                try:
                    enviadas = self.bot.scheduler.processar_todos_vencidos(chat_id_usuario=chat_id, forcar_reprocesso=False)
                except Exception as e:
                    logger.error(f"Erro ao processar vencidos após alterar horário de verificação: {e}")
            
            # Mostrar feedback de quantas mensagens foram enviadas
            if enviadas > 0:
                self.bot.send_message(chat_id, f"📧 {enviadas} mensagens enviadas para clientes vencidos", parse_mode='Markdown')
            else:
                self.bot.send_message(chat_id, "✅ Nenhum cliente vencido para processar no momento", parse_mode='Markdown')
            
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de verificação: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_limpeza(self, chat_id, novo_hhmm_digits):
        try:
            hh, mm = int(novo_hhmm_digits[:2]), int(novo_hhmm_digits[2:])
            valor = f"{hh:02d}:{mm:02d}"
            self._salvar_config(chat_id, CHAVE_LIMPEZA_CANONICA, valor)
            self.bot.send_message(chat_id, f"✅ Horário de *limpeza* alterado para `{valor}`", parse_mode='Markdown')
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de limpeza: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    # ===================== Entradas personalizadas =====================
    def _validar_hhmm(self, texto):
        return bool(re.match(r'^([0-1][0-9]|2[0-3]):([0-5][0-9])$', texto or ''))

    def horario_personalizado_envio(self, chat_id):
        self.bot.conversation_states[chat_id] = 'aguardando_horario_envio'
        self.bot.send_message(
            chat_id,
            "⌨️ Envie o novo horário de *envio* no formato HH:MM",
            parse_mode='Markdown',
            reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]}
        )

    def horario_personalizado_verificacao(self, chat_id):
        self.bot.conversation_states[chat_id] = 'aguardando_horario_verificacao'
        self.bot.send_message(
            chat_id,
            "⌨️ Envie o novo horário de *verificação* no formato HH:MM",
            parse_mode='Markdown',
            reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]}
        )

    def horario_personalizado_limpeza(self, chat_id):
        self.bot.conversation_states[chat_id] = 'aguardando_horario_limpeza'
        self.bot.send_message(
            chat_id,
            "⌨️ Envie o novo horário de *limpeza* no formato HH:MM",
            parse_mode='Markdown',
            reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]}
        )

    def processar_horario_personalizado(self, chat_id, texto, estado=None):
        try:
            if not self._validar_hhmm(texto):
                self.bot.send_message(chat_id, "❌ Formato inválido. Use HH:MM (ex.: 09:30). Tente novamente:")
                return False
            estado = estado or self.bot.conversation_states.get(chat_id)
            hhmm_digits = texto.replace(':', '')
            
            # Processar de acordo com o estado
            if estado == 'aguardando_horario_envio':
                self.set_horario_envio(chat_id, hhmm_digits)
            elif estado == 'aguardando_horario_verificacao':
                self.set_horario_verificacao(chat_id, hhmm_digits)
            elif estado == 'aguardando_horario_limpeza':
                # Para limpeza, não precisa processar vencidos
                self.set_horario_limpeza(chat_id, hhmm_digits)
            else:
                self.bot.send_message(chat_id, "❌ Estado inválido. Volte ao menu de horários.")
                return False
            self.bot.conversation_states.pop(chat_id, None)
            return True
        except Exception as e:
            logger.error(f"Erro ao processar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao processar horário personalizado.")
            return False

    # ===================== Utilitários =====================
    def status_jobs(self, chat_id):
        """Exibe status dos jobs (se seu wrapper de scheduler estiver presente)."""
        try:
            sched_wrapper = getattr(self.bot, 'scheduler', None)
            if not sched_wrapper or not getattr(sched_wrapper, 'scheduler', None):
                self.bot.send_message(chat_id, "❌ Agendador não disponível.")
                return
            sched = sched_wrapper.scheduler
            jobs = sched.get_jobs()

            mensagem = "📊 *STATUS DOS JOBS ATIVOS:*\n\n"
            if not jobs:
                mensagem += "❌ Nenhum job ativo encontrado."
            else:
                for job in jobs:
                    try:
                        brasilia = self.timezone
                        agora = datetime.now(brasilia)
                        next_run_time = job.trigger.get_next_fire_time(None, agora)
                        prox = next_run_time.astimezone(brasilia).strftime('%d/%m %H:%M:%S') if next_run_time else 'N/A'
                    except Exception as e:
                        prox = 'N/A'
                        logger.warning(f"Erro ao calcular próxima execução para {job.id}: {e}")
                    nome = getattr(job, 'name', job.id)
                    mensagem += f"• {nome}\n  ID: `{job.id}`\n  Próxima execução: {prox}\n\n"

            self.bot.send_message(chat_id, mensagem, parse_mode='Markdown',
                                  reply_markup={'inline_keyboard': [
                                      [{'text': '🔄 Recriar Jobs', 'callback_data': 'recriar_jobs'}],
                                      [{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}]
                                  ]})
        except Exception as e:
            logger.error(f"Erro ao mostrar status dos jobs: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar status dos jobs.")

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
            self._salvar_config(chat_id, CHAVE_ENVIO_CANONICA,   '09:00')
            self._salvar_config(chat_id, CHAVE_VERIF_CANONICA,   '09:00')
            self._salvar_config(chat_id, CHAVE_LIMPEZA_CANONICA, '02:00')
            if getattr(self.bot, 'db', None):
                self.bot.db.salvar_configuracao(CHAVE_TZ, 'America/Sao_Paulo', chat_id_usuario=chat_id)

            # Processar imediatamente todos os clientes vencidos deste usuário após reset
            enviadas = 0
            if hasattr(self.bot, 'scheduler') and hasattr(self.bot.scheduler, 'processar_todos_vencidos'):
                try:
                    enviadas = self.bot.scheduler.processar_todos_vencidos(chat_id_usuario=chat_id, forcar_reprocesso=False)
                except Exception as e:
                    logger.error(f"Erro ao processar vencidos após resetar horários: {e}")

            self._reprogramar_jobs_seguro()

            # Mensagem combinada com feedback
            mensagem = "✅ Horários resetados para padrão: 09:00 / 09:00 / 02:00"
            if enviadas > 0:
                mensagem += f"\n📧 {enviadas} mensagens enviadas para clientes vencidos"
            else:
                mensagem += "\n✅ Nenhum cliente vencido para processar no momento"
            
            self.bot.send_message(chat_id, mensagem)
        except Exception as e:
            logger.error(f"Erro ao resetar horários padrão: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao resetar horários: {str(e)}")

"""
Configurações de Horários do Sistema
Funções para alterar horários de verificação, envio e limpeza via bot
"""

import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class ScheduleConfig:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.timezone = pytz.timezone('America/Sao_Paulo')
        
    def config_horarios_menu(self, chat_id):
        """Menu principal de configuração de horários"""
        try:
            agora = datetime.now(self.timezone)
            mensagem = f"""⏰ CONFIGURAÇÕES DE HORÁRIOS

📅 Horários Atuais (Brasília):
🕘 Envio Diário: 09:00
   └ Mensagens são enviadas automaticamente

🕔 Verificação: 09:00  
   └ Sistema verifica vencimentos e adiciona à fila

🕚 Limpeza: 02:00
   └ Remove mensagens antigas da fila

🌍 Timezone: America/Sao_Paulo
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
                    {'text': '🔙 Voltar', 'callback_data': 'voltar_configs'},
                    {'text': '🏠 Menu Principal', 'callback_data': 'menu_principal'}
                ]
            ]

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao mostrar menu de horários: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar configurações de horários.")

    def edit_horario_envio(self, chat_id):
        """Configurar horário de envio de mensagens"""
        try:
            mensagem = """📤 ALTERAR HORÁRIO DE ENVIO

⏰ Atual: 9:00 AM (Brasília)

Este horário define quando as mensagens da fila são processadas e enviadas via WhatsApp.

💡 Recomendações:
• Horário comercial (8h-18h)
• Evitar madrugada e noite
• Considere o perfil dos seus clientes

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            horarios = ['06:00', '07:00', '08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00']
            
            # Criar botões de horário em linhas de 3
            for i in range(0, len(horarios), 3):
                linha = []
                for j in range(3):
                    if i + j < len(horarios):
                        horario = horarios[i + j]
                        linha.append({'text': horario, 'callback_data': f'set_envio_{horario.replace(":", "")}'})
                inline_keyboard.append(linha)

            # Adicionar opção personalizada
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_envio'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao configurar horário de envio: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_verificacao(self, chat_id):
        """Configurar horário de verificação diária"""
        try:
            mensagem = """🔔 ALTERAR HORÁRIO DE VERIFICAÇÃO

⏰ Atual: 9:00 AM (Brasília)

Esta verificação acontece uma vez por dia e:
• Verifica todos os clientes vencendo
• Agenda mensagens para o dia
• Envia alerta para o administrador

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            horarios = ['05:00', '06:00', '07:00', '08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00']
            
            # Criar botões de horário em linhas de 3
            for i in range(0, len(horarios), 3):
                linha = []
                for j in range(3):
                    if i + j < len(horarios):
                        horario = horarios[i + j]
                        linha.append({'text': horario, 'callback_data': f'set_verificacao_{horario.replace(":", "")}'})
                inline_keyboard.append(linha)

            # Adicionar opção personalizada
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_verificacao'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao configurar horário de verificação: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_limpeza(self, chat_id):
        """Configurar horário de limpeza da fila"""
        try:
            mensagem = """🧹 ALTERAR HORÁRIO DE LIMPEZA

⏰ Atual: 2:00 AM (Brasília)

Esta limpeza remove mensagens antigas da fila que não foram enviadas.

💡 Recomendação: Madrugada (menos impacto no sistema)

🕐 Escolha o novo horário:"""

            inline_keyboard = []
            horarios = ['01:00', '02:00', '03:00', '04:00', '05:00', '23:00', '00:00']
            
            # Criar botões de horário em linhas de 3
            for i in range(0, len(horarios), 3):
                linha = []
                for j in range(3):
                    if i + j < len(horarios):
                        horario = horarios[i + j]
                        linha.append({'text': horario, 'callback_data': f'set_limpeza_{horario.replace(":", "")}'})
                inline_keyboard.append(linha)

            # Adicionar opção personalizada
            inline_keyboard.append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_limpeza'}])
            inline_keyboard.append([{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}])

            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao configurar horário de limpeza: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def set_horario_envio(self, chat_id, novo_horario):
        """Define novo horário de envio"""
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            
            # Salvar configuração no banco
            self.bot.db.salvar_configuracao('horario_envio', f'{novo_horario[:2]}:{novo_horario[2:]}')
            
            # Recriar job de envio com novo horário usando o ID original
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                from apscheduler.triggers.cron import CronTrigger
                
                # Atualizar o job original com novo horário
                self.bot.scheduler.scheduler.add_job(
                    func=self.bot.scheduler._processar_envio_diario_9h,
                    trigger=CronTrigger(hour=hora, minute=minuto, timezone=self.bot.scheduler.scheduler.timezone),
                    id='envio_diario_9h',  # Usar o ID original
                    name=f'Envio Diário às {novo_horario[:2]}:{novo_horario[2:]}',
                    replace_existing=True
                )
                
                mensagem = f"✅ Horário de envio alterado para {novo_horario[:2]}:{novo_horario[2:]}!\n\n"
                mensagem += f"📅 Próximo envio: {self._get_next_run_time('envio_diario_9h')}"
            else:
                mensagem = "❌ Agendador não disponível."
            
            self.bot.send_message(chat_id, mensagem)
            # Voltar ao menu de horários
            self.config_horarios_menu(chat_id)
            
        except Exception as e:
            logger.error(f"Erro ao definir horário de envio: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao alterar horário.")

    def set_horario_verificacao(self, chat_id, novo_horario):
        """Define novo horário de verificação"""
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            
            # Salvar configuração no banco
            self.bot.db.salvar_configuracao('horario_verificacao', f'{novo_horario[:2]}:{novo_horario[2:]}')
            
            # Recriar job de alerta admin com novo horário usando o ID original
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                from apscheduler.triggers.cron import CronTrigger
                
                # Atualizar o job original com novo horário
                self.bot.scheduler.scheduler.add_job(
                    func=self.bot.scheduler._enviar_alerta_admin,
                    trigger=CronTrigger(hour=hora, minute=minuto, timezone=self.bot.scheduler.scheduler.timezone),
                    id='alerta_admin',  # Usar o ID original
                    name=f'Verificação Diária às {novo_horario[:2]}:{novo_horario[2:]}',
                    replace_existing=True
                )
                
                mensagem = f"✅ Horário de verificação alterado para {novo_horario[:2]}:{novo_horario[2:]}!\n\n"
                mensagem += f"📅 Próxima verificação: {self._get_next_run_time('alerta_admin')}"
            else:
                mensagem = "❌ Agendador não disponível."
            
            self.bot.send_message(chat_id, mensagem)
            # Voltar ao menu de horários
            self.config_horarios_menu(chat_id)
            
        except Exception as e:
            logger.error(f"Erro ao definir horário de verificação: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao alterar horário.")

    def set_horario_limpeza(self, chat_id, novo_horario):
        """Define novo horário de limpeza"""
        try:
            hora = int(novo_horario[:2])
            minuto = int(novo_horario[2:])
            
            # Salvar configuração no banco
            self.bot.db.salvar_configuracao('horario_limpeza', f'{novo_horario[:2]}:{novo_horario[2:]}')
            
            # Recriar job de limpeza com novo horário usando o ID original
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                from apscheduler.triggers.cron import CronTrigger
                
                # Atualizar o job original com novo horário
                self.bot.scheduler.scheduler.add_job(
                    func=self.bot.scheduler._limpar_fila_antiga,
                    trigger=CronTrigger(hour=hora, minute=minuto, timezone=self.bot.scheduler.scheduler.timezone),
                    id='limpar_fila',  # Usar o ID original
                    name=f'Limpeza da Fila às {novo_horario[:2]}:{novo_horario[2:]}',
                    replace_existing=True
                )
                
                mensagem = f"✅ Horário de limpeza alterado para {novo_horario[:2]}:{novo_horario[2:]}!\n\n"
                mensagem += f"📅 Próxima limpeza: {self._get_next_run_time('limpar_fila')}"
            else:
                mensagem = "❌ Agendador não disponível."
            
            self.bot.send_message(chat_id, mensagem)
            # Voltar ao menu de horários
            self.config_horarios_menu(chat_id)
            
        except Exception as e:
            logger.error(f"Erro ao definir horário de limpeza: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao alterar horário.")

    def recriar_jobs(self, chat_id):
        """Recria todos os jobs do agendador com limpeza completa"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                # Parar scheduler completamente
                if self.bot.scheduler.running:
                    self.bot.scheduler.scheduler.shutdown(wait=True)
                    self.bot.scheduler.running = False
                
                # Limpar todos os jobs existentes
                jobs = self.bot.scheduler.scheduler.get_jobs()
                for job in jobs:
                    self.bot.scheduler.scheduler.remove_job(job.id)
                
                logger.info(f"Removidos {len(jobs)} jobs existentes")
                
                # Recriar scheduler do zero
                from apscheduler.schedulers.background import BackgroundScheduler
                import pytz
                
                self.bot.scheduler.scheduler = BackgroundScheduler(
                    timezone=pytz.timezone('America/Sao_Paulo'),
                    job_defaults={
                        'coalesce': True,
                        'max_instances': 1,
                        'misfire_grace_time': 300
                    }
                )
                
                # Recriar jobs principais
                self.bot.scheduler._setup_main_jobs()
                
                # Reiniciar scheduler
                self.bot.scheduler.start()
                
                # Verificar jobs criados
                jobs_criados = len(self.bot.scheduler.scheduler.get_jobs())
                
                mensagem = f"✅ Scheduler recriado com sucesso!\n"
                mensagem += f"📊 {jobs_criados} jobs ativos"
                
            else:
                mensagem = "❌ Agendador não disponível."
            
            self.bot.send_message(chat_id, mensagem)
            
        except Exception as e:
            logger.error(f"Erro ao recriar jobs: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao recriar jobs: {str(e)}")
    
    def limpar_duplicatas(self, chat_id):
        """Remove jobs duplicados deixando apenas os únicos necessários"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                jobs = self.bot.scheduler.scheduler.get_jobs()
                
                # Contar jobs por ID
                job_counts = {}
                jobs_para_remover = []
                
                for job in jobs:
                    if job.id in job_counts:
                        job_counts[job.id] += 1
                        jobs_para_remover.append(job)
                    else:
                        job_counts[job.id] = 1
                
                # Remover duplicatas
                for job in jobs_para_remover:
                    self.bot.scheduler.scheduler.remove_job(job.id)
                
                # Garantir que temos apenas 3 jobs únicos
                jobs_restantes = self.bot.scheduler.scheduler.get_jobs()
                if len(jobs_restantes) != 3:
                    # Recriar jobs do zero se não temos exatamente 3
                    for job in jobs_restantes:
                        self.bot.scheduler.scheduler.remove_job(job.id)
                    
                    self.bot.scheduler._setup_main_jobs()
                
                jobs_final = len(self.bot.scheduler.scheduler.get_jobs())
                mensagem = f"✅ Limpeza concluída!\n📊 Jobs ativos: {jobs_final}"
                
                if len(jobs_para_remover) > 0:
                    mensagem += f"\n🗑️ Removidas {len(jobs_para_remover)} duplicatas"
            
            else:
                mensagem = "❌ Agendador não disponível."
            
            self.bot.send_message(chat_id, mensagem)
            
        except Exception as e:
            logger.error(f"Erro ao limpar duplicatas: {e}")
            self.bot.send_message(chat_id, f"❌ Erro na limpeza: {str(e)}")

    def status_jobs(self, chat_id):
        """Mostra status dos jobs ativos"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                jobs = self.bot.scheduler.scheduler.get_jobs()
                
                mensagem = "📊 STATUS DOS JOBS ATIVOS:\n\n"
                
                for job in jobs:
                    # Corrigir acesso a next_run_time
                    try:
                        # Usar o trigger para calcular próxima execução
                        from datetime import datetime
                        import pytz
                        brasilia = pytz.timezone('America/Sao_Paulo')
                        agora = datetime.now(brasilia)
                        
                        next_run_time = job.trigger.get_next_fire_time(None, agora)
                        if next_run_time:
                            next_run_br = next_run_time.astimezone(brasilia)
                            next_run = next_run_br.strftime('%d/%m %H:%M')
                        else:
                            next_run = 'N/A'
                    except Exception as e:
                        next_run = 'N/A'
                        logger.warning(f"Erro ao calcular próxima execução para {job.id}: {e}")
                    
                    job_name = getattr(job, 'name', job.id)
                    mensagem += f"• {job_name}\n  ID: {job.id}\n  Próxima execução: {next_run}\n\n"
                
                if not jobs:
                    mensagem += "❌ Nenhum job ativo encontrado."
            else:
                mensagem = "❌ Agendador não disponível."
            
            inline_keyboard = [
                [{'text': '🔄 Recriar Jobs', 'callback_data': 'recriar_jobs'}],
                [{'text': '🧹 Limpar Duplicatas', 'callback_data': 'limpar_duplicatas'}],
                [{'text': '🔙 Voltar Horários', 'callback_data': 'config_horarios'}]
            ]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})
            
        except Exception as e:
            logger.error(f"Erro ao mostrar status dos jobs: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar status dos jobs.")

    def horario_personalizado_envio(self, chat_id):
        """Solicita horário personalizado para envio"""
        try:
            mensagem = """⌨️ HORÁRIO PERSONALIZADO - ENVIO

Digite o horário desejado no formato HH:MM

💡 Exemplos:
• 08:30 (8h30 da manhã)
• 14:15 (2h15 da tarde)
• 19:45 (7h45 da noite)

⚠️ Use formato 24 horas (00:00 a 23:59)"""

            # Aguardar resposta do usuário
            self.bot.conversation_states[chat_id] = 'aguardando_horario_envio'
            
            inline_keyboard = [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def horario_personalizado_verificacao(self, chat_id):
        """Solicita horário personalizado para verificação"""
        try:
            mensagem = """⌨️ HORÁRIO PERSONALIZADO - VERIFICAÇÃO

Digite o horário desejado no formato HH:MM

💡 Exemplos:
• 05:30 (5h30 da manhã)
• 07:00 (7h da manhã)
• 09:15 (9h15 da manhã)

⚠️ Use formato 24 horas (00:00 a 23:59)"""

            # Aguardar resposta do usuário
            self.bot.conversation_states[chat_id] = 'aguardando_horario_verificacao'
            
            inline_keyboard = [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def horario_personalizado_limpeza(self, chat_id):
        """Solicita horário personalizado para limpeza"""
        try:
            mensagem = """⌨️ HORÁRIO PERSONALIZADO - LIMPEZA

Digite o horário desejado no formato HH:MM

💡 Exemplos:
• 01:00 (1h da madrugada)
• 23:30 (11h30 da noite)
• 03:15 (3h15 da madrugada)

⚠️ Use formato 24 horas (00:00 a 23:59)
💡 Recomenda-se madrugada para menos impacto"""

            # Aguardar resposta do usuário
            self.bot.conversation_states[chat_id] = 'aguardando_horario_limpeza'
            
            inline_keyboard = [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]
            
            self.bot.send_message(chat_id, mensagem, reply_markup={'inline_keyboard': inline_keyboard})

        except Exception as e:
            logger.error(f"Erro ao solicitar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário personalizado.")

    def processar_horario_personalizado(self, chat_id, texto):
        """Processa horário personalizado digitado pelo usuário"""
        try:
            import re
            
            # Validar formato HH:MM
            padrao = r'^([0-1][0-9]|2[0-3]):([0-5][0-9])$'
            if not re.match(padrao, texto):
                self.bot.send_message(chat_id, 
                    "❌ Formato inválido!\n\n"
                    "Use o formato HH:MM (exemplo: 09:30)\n"
                    "Tente novamente:")
                return False
                
            estado = self.bot.conversation_states.get(chat_id)
            
            if estado == 'aguardando_horario_envio':
                horario_sem_dois_pontos = texto.replace(':', '')
                self.set_horario_envio(chat_id, horario_sem_dois_pontos)
                
            elif estado == 'aguardando_horario_verificacao':
                horario_sem_dois_pontos = texto.replace(':', '')
                self.set_horario_verificacao(chat_id, horario_sem_dois_pontos)
                
            elif estado == 'aguardando_horario_limpeza':
                horario_sem_dois_pontos = texto.replace(':', '')
                self.set_horario_limpeza(chat_id, horario_sem_dois_pontos)
                
            else:
                self.bot.send_message(chat_id, "❌ Estado de configuração inválido.")
                return False
            
            # Limpar estado
            if chat_id in self.bot.conversation_states:
                del self.bot.conversation_states[chat_id]
                
            return True
            
        except Exception as e:
            logger.error(f"Erro ao processar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao processar horário.")
            return False
            
    def _get_next_run_time(self, job_id):
        """Obtém próximo horário de execução de um job"""
        try:
            if hasattr(self.bot, 'scheduler') and self.bot.scheduler:
                job = self.bot.scheduler.scheduler.get_job(job_id)
                if job and job.next_run_time:
                    from utils import formatar_datetime_br
                    return formatar_datetime_br(job.next_run_time)
            return "Não agendado"
        except Exception:
            return "Erro ao obter horário"
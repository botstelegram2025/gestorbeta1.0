"""
Sistema de Agendamento de Mensagens
- Respeita horários definidos por USUÁRIO (fallback global)
- Montagem da fila às 05:00; cada mensagem do dia é agendada no HH:MM do usuário
- Worker minutal envia quando chegar o horário (America/Sao_Paulo)
- Jobs principais: verificação 05:00, alertas por usuário no horário escolhido, limpeza, worker minutal
- (Removido) job de envio diário global para evitar conflito com horários por usuário
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta, time as dtime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from utils import agora_br, formatar_data_br, formatar_datetime_br
import pytz
import time as _time

logger = logging.getLogger(__name__)


class MessageScheduler:
    def __init__(self, database_manager, baileys_api, template_manager):
        """Inicializa o agendador de mensagens"""
        self.db = database_manager
        self.baileys_api = baileys_api
        self.template_manager = template_manager

        # Usar BackgroundScheduler para compatibilidade com threading
        self.scheduler = BackgroundScheduler(
            timezone=pytz.timezone('America/Sao_Paulo'),
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300  # 5 minutos de tolerância
            }
        )
        self.tz = self.scheduler.timezone
        self.running = False
        self.ultima_verificacao_time = None

        # Configurar jobs principais
        self._setup_main_jobs()

    # ===================== Setup de Jobs =====================
    def _setup_main_jobs(self):
        """Configura os jobs principais do sistema"""
        try:
            # Horários globais (usados apenas para verificação/limpeza/alertas); envio é por USUÁRIO
            horario_envio = self._get_horario_config_global('horario_envio', '09:00')
            horario_verificacao = self._get_horario_config_global('horario_verificacao', '09:00')
            horario_limpeza = self._get_horario_config_global('horario_limpeza', '02:00')

            logger.info(f"Sistema usando horários globais (para jobs não-atômicos): Verificação {horario_verificacao}, Limpeza {horario_limpeza}")
            logger.info("Envios aos clientes são agendados por usuário (HH:MM individual)")

            # Parse com fallback seguro
            try:
                _, _ = map(int, horario_envio.split(':'))  # apenas validação
                hora_verif, min_verif = map(int, horario_verificacao.split(':'))
                hora_limp, min_limp = map(int, horario_limpeza.split(':'))
            except ValueError as e:
                logger.error(f"Erro no formato dos horários globais: {e}")
                hora_verif, min_verif = 9, 0
                hora_limp, min_limp = 2, 0

            # Limpar jobs existentes antes de criar novos
            job_ids = [
                'envio_diario_9h',           # será removido (não mais usado)
                'limpar_fila',
                'alertas_usuarios',
                'verificacao_5h',
                'processar_fila_minuto'
            ]
            for job_id in job_ids:
                try:
                    if self.scheduler.get_job(job_id):
                        self.scheduler.remove_job(job_id)
                except Exception:
                    pass

            # (Removido) Envio diário global - agora o envio é sempre por usuário
            # self.scheduler.add_job(... id='envio_diario_9h' ...)

            # Limpeza da fila no horário configurado
            self.scheduler.add_job(
                func=self._limpar_fila_antiga,
                trigger=CronTrigger(hour=hora_limp, minute=min_limp, timezone=self.scheduler.timezone),
                id='limpar_fila',
                name=f'Limpar Fila Antiga às {horario_limpeza}',
                replace_existing=True
            )

            # Alerta diário para usuários (cada um recebe somente dos seus clientes)
            self.scheduler.add_job(
                func=self._enviar_alertas_usuarios,
                trigger=CronTrigger(hour=hora_verif, minute=min_verif, timezone=self.scheduler.timezone),
                id='alertas_usuarios',
                name=f'Alertas Diários por Usuário às {horario_verificacao}',
                replace_existing=True
            )

            # Verificação diária às 05:00 para montar a fila do dia (usando horário por usuário)
            self.scheduler.add_job(
                func=self._verificar_e_agendar_mensagens_do_dia,
                trigger=CronTrigger(hour=5, minute=0, timezone=self.scheduler.timezone),
                id='verificacao_5h',
                name='Verificação diária às 05:00',
                replace_existing=True
            )

            # Worker da fila: roda todo minuto (segundo 0)
            self.scheduler.add_job(
                func=self._processar_fila_mensagens,
                trigger=CronTrigger(second=0, timezone=self.scheduler.timezone),
                id='processar_fila_minuto',
                name='Processar fila (minutal)',
                replace_existing=True,
                misfire_grace_time=60,
                coalesce=True
            )

            jobs_count = len(self.scheduler.get_jobs())
            logger.info(f"Jobs principais configurados - Verificação: {horario_verificacao}, Limpeza: {horario_limpeza} | Total: {jobs_count}")

        except Exception as e:
            logger.error(f"Erro ao configurar jobs principais: {e}")
            raise

    # ===================== Controle do Scheduler =====================
    def start(self):
        """Inicia o agendador"""
        try:
            if not self.running:
                self.scheduler.start()
                self.running = True
                logger.info("Agendador de mensagens iniciado com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao iniciar agendador: {e}")

    def stop(self):
        """Para o agendador"""
        try:
            if self.running:
                self.scheduler.shutdown()
                self.running = False
                logger.info("Agendador de mensagens parado")
        except Exception as e:
            logger.error(f"Erro ao parar agendador: {e}")

    def is_running(self):
        """Verifica se o agendador está rodando"""
        return self.running and self.scheduler.running

    def ultima_verificacao(self):
        """Retorna a última verificação formatada"""
        if self.ultima_verificacao_time:
            return formatar_datetime_br(self.ultima_verificacao_time)
        return "Nunca executado"

    # ===================== Worker da Fila =====================
    def _processar_fila_mensagens(self):
        """Processa mensagens pendentes na fila"""
        try:
            self.ultima_verificacao_time = agora_br()
            logger.info("Iniciando processamento da fila de mensagens...")

            mensagens_pendentes = self.db.obter_mensagens_pendentes(limit=50)

            if not mensagens_pendentes:
                logger.info("Nenhuma mensagem pendente para processamento")
                return

            logger.info(f"Processando {len(mensagens_pendentes)} mensagens pendentes")

            for mensagem in mensagens_pendentes:
                try:
                    ag = mensagem.get('agendado_para')
                    agora = agora_br()
                    if ag and ag > agora:
                        # ainda não é hora
                        continue
                    self._enviar_mensagem_fila(mensagem)
                    # Aguardar entre envios para não sobrecarregar
                    _time.sleep(2)
                except Exception as e:
                    logger.error(f"Erro ao processar mensagem ID {mensagem.get('id')}: {e}")
                    self.db.marcar_mensagem_processada(mensagem['id'], False, str(e))

            logger.info("Processamento da fila concluído")

        except Exception as e:
            logger.error(f"Erro no processamento da fila: {e}")

    def _enviar_mensagem_fila(self, mensagem):
        """Envia uma mensagem da fila"""
        try:
            # Verificar se cliente ainda está ativo
            cliente = self.db.buscar_cliente_por_id(mensagem['cliente_id'])
            if not cliente or not cliente.get('ativo'):
                logger.info(f"Cliente {mensagem['cliente_id']} inativo, removendo da fila")
                self.db.marcar_mensagem_processada(mensagem['id'], True)
                return

            # Enviar mensagem via Baileys - incluir chat_id_usuario obrigatório
            chat_id_usuario = mensagem.get('chat_id_usuario') or cliente.get('chat_id_usuario')
            if not chat_id_usuario:
                logger.error(f"Mensagem ID {mensagem['id']} sem chat_id_usuario - não pode enviar WhatsApp")
                self.db.marcar_mensagem_processada(mensagem['id'], False, "chat_id_usuario não encontrado")
                return

            resultado = self.baileys_api.send_message(
                phone=mensagem['telefone'],
                message=mensagem['mensagem'],
                chat_id_usuario=chat_id_usuario
            )

            if resultado and resultado.get('success'):
                # Registrar envio bem-sucedido
                self.db.registrar_envio(
                    cliente_id=mensagem['cliente_id'],
                    template_id=mensagem['template_id'],
                    telefone=mensagem['telefone'],
                    mensagem=mensagem['mensagem'],
                    tipo_envio='automatico',
                    sucesso=True,
                    message_id=resultado.get('message_id')
                )

                # Marcar como processado
                self.db.marcar_mensagem_processada(mensagem['id'], True)

                logger.info(f"Mensagem enviada com sucesso para {mensagem.get('cliente_nome')} ({mensagem['telefone']})")

            else:
                # Registrar falha
                erro = (resultado or {}).get('error', 'Erro desconhecido')

                self.db.registrar_envio(
                    cliente_id=mensagem['cliente_id'],
                    template_id=mensagem['template_id'],
                    telefone=mensagem['telefone'],
                    mensagem=mensagem['mensagem'],
                    tipo_envio='automatico',
                    sucesso=False,
                    erro=erro
                )

                # Incrementar tentativas
                self.db.marcar_mensagem_processada(mensagem['id'], False, erro)

                logger.error(f"Falha ao enviar mensagem para {mensagem.get('cliente_nome')}: {erro}")

        except Exception as e:
            logger.error(f"Erro ao enviar mensagem da fila: {e}")
            try:
                self.db.marcar_mensagem_processada(mensagem['id'], False, str(e))
            except Exception:
                pass

    # ===================== Envio diário por usuário (LEGADO / opcional) =====================
    def _processar_envio_diario_9h(self):
        """Mantido para compatibilidade/uso manual. NÃO é mais agendado automaticamente."""
        try:
            logger.info("=== ENVIO DIÁRIO (manual) ===")
            hoje = agora_br().date()
            usuarios_ativos = self._obter_usuarios_ativos()
            if not usuarios_ativos:
                logger.info("Nenhum usuário ativo encontrado para processamento manual")
                return
            enviadas_total = 0
            for usuario in usuarios_ativos:
                chat_id_usuario = usuario['chat_id']
                enviadas_total += self._processar_clientes_usuario(chat_id_usuario, hoje)
            logger.info(f"=== ENVIO (manual) CONCLUÍDO: {enviadas_total} mensagens ===")
        except Exception as e:
            logger.error(f"Erro no envio diário (manual): {e}")

    # ===================== Utilidades de Usuário/Clientes =====================
    def _obter_usuarios_ativos(self):
        """Obtém lista de usuários ativos do sistema"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT chat_id, nome
                    FROM usuarios 
                    WHERE plano_ativo = true
                    AND (status = 'ativo' OR status = 'teste_gratuito')
                    ORDER BY chat_id
                    """
                )
                usuarios = cursor.fetchall()
                return [dict(usuario) for usuario in usuarios]
        except Exception as e:
            logger.error(f"Erro ao obter usuários ativos: {e}")
            return []

    def _processar_clientes_usuario(self, chat_id_usuario, hoje):
        """Processa clientes de um usuário específico (envio imediato, fora da fila)"""
        try:
            # Verificar se este usuário tem horário personalizado de envio (somente log informativo)
            horario_usuario = self._get_horario_config_usuario('horario_envio', chat_id_usuario, None)
            if horario_usuario:
                hora_atual = agora_br().strftime('%H:%M')
                if horario_usuario != hora_atual[:5]:
                    logger.info(f"Usuário {chat_id_usuario} tem horário personalizado {horario_usuario}, mas execução manual agora é {hora_atual}")

            # Buscar clientes APENAS deste usuário
            clientes = self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=chat_id_usuario)
            if not clientes:
                logger.debug(f"Usuário {chat_id_usuario}: Nenhum cliente ativo encontrado")
                return 0

            enviadas = 0
            for cliente in clientes:
                try:
                    vencimento = cliente['vencimento']
                    dias_vencimento = (vencimento - hoje).days

                    if dias_vencimento == -1:
                        if self._enviar_mensagem_cliente(cliente, 'vencimento_1dia_apos', chat_id_usuario):
                            enviadas += 1
                    elif dias_vencimento == 0:
                        if self._enviar_mensagem_cliente(cliente, 'vencimento_hoje', chat_id_usuario):
                            enviadas += 1
                    elif dias_vencimento in (1, 2):
                        if self._enviar_mensagem_cliente(cliente, 'vencimento_2dias', chat_id_usuario):
                            enviadas += 1
                except Exception as e:
                    logger.error(f"Erro ao processar cliente {cliente.get('nome')}: {e}")
            return enviadas
        except Exception as e:
            logger.error(f"Erro ao processar clientes do usuário {chat_id_usuario}: {e}")
            return 0

    def processar_todos_vencidos(self, forcar_reprocesso=False):
        """Processa TODOS os clientes vencidos (independente de quantos dias)."""
        try:
            logger.info("=== PROCESSAMENTO FORÇADO DE TODOS OS VENCIDOS ===")
            clientes = self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=None)
            if not clientes:
                logger.info("Nenhum cliente ativo encontrado")
                return 0

            enviadas = 0
            hoje = agora_br().date()
            for cliente in clientes:
                try:
                    vencimento = cliente['vencimento']
                    dias_vencimento = (vencimento - hoje).days

                    if dias_vencimento < 0:
                        template = self.db.obter_template_por_tipo('vencimento_1dia_apos', cliente.get('chat_id_usuario'))
                        if template and not forcar_reprocesso and self._ja_enviada_hoje(cliente['id'], template['id']):
                            logger.info(f"⏭️  {cliente['nome']} - mensagem já enviada hoje")
                            continue
                        if self._enviar_mensagem_cliente(cliente, 'vencimento_1dia_apos', cliente.get('chat_id_usuario')):
                            enviadas += 1
                    elif dias_vencimento in (0, 1, 2):
                        tipo = 'vencimento_hoje' if dias_vencimento == 0 else 'vencimento_2dias'
                        if self._enviar_mensagem_cliente(cliente, tipo, cliente.get('chat_id_usuario')):
                            enviadas += 1
                except Exception as e:
                    logger.error(f"Erro ao processar cliente {cliente['nome']}: {e}")

            logger.info(f"=== PROCESSAMENTO FORÇADO CONCLUÍDO: {enviadas} mensagens enviadas ===")
            return enviadas
        except Exception as e:
            logger.error(f"Erro no processamento forçado de vencidos: {e}")
            return 0

    # ===================== Envio imediato (template por cliente) =====================
    def _enviar_mensagem_cliente(self, cliente, tipo_template, chat_id_usuario=None):
        """Envia mensagem imediatamente para o cliente"""
        try:
            resolved_chat_id = chat_id_usuario or cliente.get('chat_id_usuario')
            if not resolved_chat_id:
                logger.error(f"Cliente {cliente.get('nome')} sem chat_id_usuario - não pode enviar WhatsApp")
                return False

            # Verificar preferências
            if not self._cliente_pode_receber_mensagem(cliente, tipo_template):
                logger.info(f"Cliente {cliente['nome']} optou por não receber mensagens do tipo {tipo_template}")
                return False

            # Buscar template com isolamento por usuário
            template = self.db.obter_template_por_tipo(tipo_template, resolved_chat_id)
            if not template:
                logger.warning(f"Template {tipo_template} não encontrado para usuário {resolved_chat_id}")
                return False

            mensagem = self.template_manager.processar_template(template['conteudo'], cliente)

            # Evitar duplicidade diária
            if self._ja_enviada_hoje(cliente['id'], template['id']):
                logger.info(f"Mensagem {tipo_template} já enviada hoje para {cliente['nome']}")
                return False

            # Enviar via WhatsApp
            resultado = self.baileys_api.send_message(cliente['telefone'], mensagem, resolved_chat_id)
            sucesso = resultado.get('success', False) if resultado else False

            if sucesso:
                self.db.registrar_envio(
                    cliente_id=cliente['id'],
                    template_id=template['id'],
                    telefone=cliente['telefone'],
                    mensagem=mensagem,
                    tipo_envio='automatico',
                    sucesso=True,
                    chat_id_usuario=resolved_chat_id
                )
                return True
            else:
                logger.error(f"Falha ao enviar mensagem para {cliente['nome']}")
                return False
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para cliente: {e}")
            return False

    def _cliente_pode_receber_mensagem(self, cliente, tipo_template):
        """Verifica se o cliente pode receber mensagens baseado nas preferências de notificação"""
        try:
            cliente_id = cliente['id']
            chat_id_usuario = cliente.get('chat_id_usuario')

            if hasattr(self.db, 'cliente_pode_receber_cobranca'):
                if tipo_template in ['vencimento_1dia_apos', 'vencimento_hoje', 'vencimento_2dias']:
                    pode_receber = self.db.cliente_pode_receber_cobranca(cliente_id, chat_id_usuario)
                    logger.info(f"Cliente {cliente['nome']}: pode receber cobrança = {pode_receber}")
                    return pode_receber
                else:
                    pode_receber = self.db.cliente_pode_receber_notificacoes(cliente_id, chat_id_usuario)
                    logger.info(f"Cliente {cliente['nome']}: pode receber notificações = {pode_receber}")
                    return pode_receber
            else:
                logger.warning("Métodos de verificação de preferências não disponíveis - permitindo envio")
                return True
        except Exception as e:
            logger.error(f"Erro ao verificar preferências de notificação: {e}")
            return True  # Em caso de erro, permitir envio para manter funcionalidade

    # ===================== Rotinas de verificação / agendamento =====================
    def _verificar_e_agendar_mensagens_do_dia(self):
        """Verifica todos os clientes às 5h e agenda APENAS mensagens que devem ser enviadas hoje (no horário do usuário)"""
        try:
            logger.info("=== VERIFICAÇÃO DIÁRIA ÀS 5H ===")
            logger.info("Verificando clientes e agendando mensagens apenas para hoje...")

            clientes = self.db.listar_clientes(apenas_ativos=True)
            if not clientes:
                logger.info("Nenhum cliente ativo encontrado")
                return

            contador_agendadas = 0
            hoje = agora_br().date()
            for cliente in clientes:
                try:
                    vencimento = cliente['vencimento']
                    dias_vencimento = (vencimento - hoje).days

                    if dias_vencimento == -1:
                        self._agendar_mensagem_vencimento(cliente, 'vencimento_1dia_apos', hoje)
                        contador_agendadas += 1
                    elif dias_vencimento < -1:
                        logger.info(f"⏭️  {cliente['nome']} vencido há {abs(dias_vencimento)} dias - ignorado no agendamento automático")
                    elif dias_vencimento == 0:
                        self._agendar_mensagem_vencimento(cliente, 'vencimento_hoje', hoje)
                        contador_agendadas += 1
                    elif dias_vencimento in (1, 2):
                        self._agendar_mensagem_vencimento(cliente, 'vencimento_2dias', hoje)
                        contador_agendadas += 1
                except Exception as e:
                    logger.error(f"Erro ao verificar cliente {cliente['nome']}: {e}")

            logger.info(f"=== VERIFICAÇÃO CONCLUÍDA: {contador_agendadas} mensagens agendadas para HOJE ===")
        except Exception as e:
            logger.error(f"Erro na verificação diária às 5h: {e}")

    def _agendar_mensagem_vencimento(self, cliente, tipo_template, data_envio):
        """Agenda mensagem específica de vencimento para envio no mesmo dia, no HH:MM do USUÁRIO."""
        try:
            # Buscar template correspondente (isolado por usuário)
            template = self.db.obter_template_por_tipo(tipo_template, chat_id_usuario=cliente.get('chat_id_usuario'))
            if not template:
                logger.warning(f"Template {tipo_template} não encontrado")
                return

            # Processar template com dados do cliente
            mensagem = self.template_manager.processar_template(template['conteudo'], cliente)

            # === HORÁRIO POR USUÁRIO ===
            agora = agora_br()
            hhmm = self._get_horario_config_usuario(
                'horario_envio',
                cliente.get('chat_id_usuario'),
                default=self._get_horario_config_global('horario_envio', '12:00')
            )
            try:
                h, m = map(int, str(hhmm).split(':'))
            except Exception:
                h, m = 12, 0  # fallback robusto

            alvo = self.tz.localize(datetime.combine(data_envio, dtime(h, m)))

            # Se já passou do horário do usuário hoje, manda ainda hoje em até 10 minutos
            if agora > alvo:
                limite_hoje = agora.replace(hour=23, minute=59, second=0, microsecond=0)
                alvo = min(agora + timedelta(minutes=10), limite_hoje)

            # Evitar duplicata para o mesmo dia
            if self.db.verificar_mensagem_existente(cliente['id'], template['id'], data_envio):
                logger.info(f"Mensagem {tipo_template} já agendada para {cliente['nome']}")
                return

            # Adicionar na fila para o horário do usuário
            self.db.adicionar_fila_mensagem(
                cliente_id=cliente['id'],
                template_id=template['id'],
                telefone=cliente['telefone'],
                mensagem=mensagem,
                tipo_mensagem=tipo_template,
                agendado_para=alvo
            )

            logger.info(f"Mensagem {tipo_template} agendada para {cliente['nome']} - ENVIO: {alvo.strftime('%d/%m/%Y %H:%M')}")

        except Exception as e:
            logger.error(f"Erro ao agendar mensagem de vencimento: {e}")

    # ===================== Limpeza / Cancelamento =====================
    def _limpar_fila_antiga(self):
        """Remove mensagens antigas processadas da fila e mensagens futuras desnecessárias"""
        try:
            logger.info("Iniciando limpeza da fila antiga...")
            removidas_antigas = self.db.limpar_fila_processadas(dias=7)
            removidas_futuras = self.db.limpar_mensagens_futuras()
            logger.info(f"Limpeza concluída: {removidas_antigas} mensagens antigas e {removidas_futuras} mensagens futuras removidas")
        except Exception as e:
            logger.error(f"Erro na limpeza da fila: {e}")

    def cancelar_mensagens_cliente_renovado(self, cliente_id):
        """Cancela todas as mensagens pendentes na fila quando cliente é renovado"""
        try:
            logger.info(f"Cancelando mensagens na fila para cliente renovado ID: {cliente_id}")
            mensagens_pendentes = self.db.buscar_mensagens_fila_cliente(cliente_id, apenas_pendentes=True)
            if not mensagens_pendentes:
                logger.info(f"Nenhuma mensagem pendente encontrada para cliente ID: {cliente_id}")
                return 0
            canceladas = 0
            for mensagem in mensagens_pendentes:
                try:
                    if self.db.cancelar_mensagem_fila(mensagem['id']):
                        canceladas += 1
                        logger.info(f"Mensagem ID {mensagem['id']} cancelada (cliente renovado)")
                except Exception as e:
                    logger.error(f"Erro ao cancelar mensagem ID {mensagem.get('id', 'unknown')}: {e}")
            logger.info(f"Cliente renovado: {canceladas} mensagens canceladas da fila")
            return canceladas
        except Exception as e:
            logger.error(f"Erro ao cancelar mensagens de cliente renovado: {e}")
            return 0

    # ===================== Alertas (admin/usuário) =====================
    def _enviar_alertas_usuarios(self):
        """Envia alerta diário isolado para cada usuário sobre APENAS seus clientes e dispara alertas do sistema."""
        try:
            import os
            logger.info("Enviando alertas diários isolados por usuário...")

            # Dispara alertas do sistema (teste/renovação) para amanhã
            try:
                amanha = agora_br().date() + timedelta(days=1)
                self._verificar_usuarios_sistema(amanha)
            except Exception as e:
                logger.warning(f"Falha nos alertas do sistema: {e}")

            usuarios_ativos = self._obter_usuarios_ativos()
            if not usuarios_ativos:
                logger.info("Nenhum usuário ativo para envio de alertas")
                return

            for usuario in usuarios_ativos:
                chat_id_usuario = usuario['chat_id']
                try:
                    self._enviar_alerta_usuario_individual(chat_id_usuario)
                except Exception as e:
                    logger.error(f"Erro ao enviar alerta para usuário {chat_id_usuario}: {e}")

            logger.info(f"Alertas enviados para {len(usuarios_ativos)} usuários")
        except Exception as e:
            logger.error(f"Erro no envio de alertas diários: {e}")

    def _enviar_alerta_usuario_individual(self, chat_id_usuario):
        """Envia alerta individual para um usuário específico sobre APENAS seus clientes"""
        try:
            import os
            logger.info(f"Enviando alerta diário para usuário {chat_id_usuario}...")

            # Loga preferência individual (execução é centralizada)
            horario_alerta_usuario = self._get_horario_config_usuario('horario_verificacao', chat_id_usuario, None)
            if horario_alerta_usuario:
                hora_atual = agora_br().strftime('%H:%M')
                if horario_alerta_usuario != hora_atual[:5]:
                    logger.info(f"Usuário {chat_id_usuario} prefere alertas às {horario_alerta_usuario}, mas executando no horário global por eficiência")

            hoje = agora_br().date()
            clientes_hoje, clientes_proximos, clientes_vencidos = [], [], []

            clientes = self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=chat_id_usuario)
            for cliente in clientes:
                try:
                    vencimento = cliente['vencimento']
                    dias_diferenca = (vencimento - hoje).days
                    if dias_diferenca == 0:
                        clientes_hoje.append(cliente)
                    elif 1 <= dias_diferenca <= 7:
                        clientes_proximos.append(cliente)
                    elif dias_diferenca < 0:
                        clientes_vencidos.append(cliente)
                except Exception as e:
                    logger.error(f"Erro ao processar cliente {cliente.get('nome', 'unknown')}: {e}")

            if clientes_hoje or clientes_proximos or clientes_vencidos:
                mensagem = f"""🚨 *ALERTA DIÁRIO - VENCIMENTOS*
📅 *{hoje.strftime('%d/%m/%Y')}*

"""
                if clientes_vencidos:
                    mensagem += f"🔴 *VENCIDOS ({len(clientes_vencidos)}):*\n"
                    for cliente in clientes_vencidos[:5]:
                        dias_vencido = abs((cliente['vencimento'] - hoje).days)
                        mensagem += f"• {cliente['nome']} - há {dias_vencido} dias\n"
                    if len(clientes_vencidos) > 5:
                        mensagem += f"• +{len(clientes_vencidos) - 5} outros vencidos\n"
                    mensagem += "\n"
                if clientes_hoje:
                    mensagem += f"⚠️ *VENCEM HOJE ({len(clientes_hoje)}):*\n"
                    for cliente in clientes_hoje:
                        mensagem += f"• {cliente['nome']} - R$ {cliente['valor']:.2f}\n"
                    mensagem += "\n"
                if clientes_proximos:
                    mensagem += f"📅 *PRÓXIMOS 7 DIAS ({len(clientes_proximos)}):*\n"
                    for cliente in clientes_proximos[:5]:
                        dias_restantes = (cliente['vencimento'] - hoje).days
                        mensagem += f"• {cliente['nome']} - {dias_restantes} dias\n"
                    if len(clientes_proximos) > 5:
                        mensagem += f"• +{len(clientes_proximos) - 5} outros próximos\n"
                    mensagem += "\n"
                mensagem += f"""📊 *RESUMO:*
• Total clientes ativos: {len(clientes)}
• Vencidos: {len(clientes_vencidos)}
• Vencem hoje: {len(clientes_hoje)}
• Próximos 7 dias: {len(clientes_proximos)}

💡 Use o comando `/vencimentos` para ver detalhes"""

                admin_chat_id = os.getenv('ADMIN_CHAT_ID')
                if admin_chat_id:
                    self._enviar_para_admin(admin_chat_id, mensagem)
                else:
                    logger.warning("ADMIN_CHAT_ID não configurado para alerta")
            else:
                mensagem = f"""✅ *RELATÓRIO DIÁRIO*
📅 *{hoje.strftime('%d/%m/%Y')}*

🎉 Nenhum cliente vencendo hoje!
📊 Total de clientes ativos: {len(clientes)}

Tudo sob controle! 👍"""
                admin_chat_id = os.getenv('ADMIN_CHAT_ID')
                if admin_chat_id:
                    self._enviar_para_admin(admin_chat_id, mensagem)

            logger.info("Alerta diário enviado para administrador")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta para administrador: {e}")

    def _enviar_para_admin(self, admin_chat_id, mensagem):
        """Envia mensagem para o administrador via Telegram"""
        try:
            import requests
            import os

            bot_token = os.getenv('BOT_TOKEN')
            if not bot_token:
                logger.error("BOT_TOKEN não configurado para envio de alerta")
                return

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': admin_chat_id,
                'text': mensagem,
                'parse_mode': 'Markdown'
            }

            response = requests.post(url, data=data, timeout=10)

            if response.status_code == 200:
                logger.info("Alerta enviado com sucesso para administrador")
            else:
                logger.error(f"Erro ao enviar alerta: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para admin: {e}")

    # ===================== Usuários do sistema (teste/renovação) =====================
    def _verificar_usuarios_sistema(self, data_vencimento):
        """Verifica usuários do sistema que precisam de alerta de pagamento"""
        try:
            self._verificar_usuarios_teste_vencendo(data_vencimento)
            self._verificar_usuarios_pagos_vencendo(data_vencimento)
        except Exception as e:
            logger.error(f"Erro ao verificar usuários do sistema: {e}")

    def _verificar_usuarios_teste_vencendo(self, data_vencimento):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT chat_id, nome, email, fim_periodo_teste
                    FROM usuarios 
                    WHERE status = 'teste_gratuito' 
                    AND plano_ativo = true
                    AND DATE(fim_periodo_teste) = %s
                    """,
                    (data_vencimento,)
                )
                usuarios_vencendo = cursor.fetchall()
            if usuarios_vencendo:
                logger.info(f"Encontrados {len(usuarios_vencendo)} usuários em teste vencendo em {data_vencimento}")
                for usuario in usuarios_vencendo:
                    try:
                        self._enviar_alerta_teste_vencendo(dict(usuario))
                    except Exception as e:
                        logger.error(f"Erro ao enviar alerta para usuário {usuario.get('chat_id')}: {e}")
        except Exception as e:
            logger.error(f"Erro ao verificar usuários em teste vencendo: {e}")

    def _verificar_usuarios_pagos_vencendo(self, data_vencimento):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT chat_id, nome, email, proximo_vencimento
                    FROM usuarios 
                    WHERE status = 'pago' 
                    AND plano_ativo = true
                    AND DATE(proximo_vencimento) = %s
                    """,
                    (data_vencimento,)
                )
                usuarios_vencendo = cursor.fetchall()
            if usuarios_vencendo:
                logger.info(f"Encontrados {len(usuarios_vencendo)} usuários pagos vencendo em {data_vencimento}")
                for usuario in usuarios_vencendo:
                    try:
                        self._enviar_alerta_renovacao(dict(usuario))
                    except Exception as e:
                        logger.error(f"Erro ao enviar alerta de renovação para usuário {usuario.get('chat_id')}: {e}")
        except Exception as e:
            logger.error(f"Erro ao verificar usuários pagos vencendo: {e}")

    def _enviar_alerta_teste_vencendo(self, usuario):
        try:
            chat_id = usuario.get('chat_id')
            nome = usuario.get('nome', 'usuário')
            fim_teste = usuario.get('fim_periodo_teste')
            if isinstance(fim_teste, datetime):
                data_vencimento = fim_teste.strftime('%d/%m/%Y')
            else:
                data_vencimento = 'amanhã'
            mensagem = f"""⚠️ *TESTE GRATUITO VENCENDO!*

Olá {nome}! 👋

Seu período de teste gratuito vence *{data_vencimento}*.

Para continuar usando o sistema sem interrupções, você precisa ativar um plano pago.

💡 *Plano mensal:* R$ 20,00
✅ *Acesso completo a todas as funcionalidades*
📱 *Gestão de clientes pelo Telegram*
📊 *Relatórios e análises*
📞 *Suporte prioritário*

Garanta já seu acesso! 👇"""
            inline_keyboard = [
                [
                    {'text': '💳 Gerar PIX - R$ 20,00', 'callback_data': f'gerar_pix_usuario_{chat_id}'},
                ],
                [
                    {'text': '📞 Falar com Suporte', 'url': 'https://t.me/seu_suporte'},
                    {'text': '❓ Dúvidas', 'callback_data': 'info_planos'}
                ]
            ]
            if hasattr(self, 'bot') and self.bot:
                self.bot.send_message(
                    chat_id,
                    mensagem,
                    parse_mode='Markdown',
                    reply_markup={'inline_keyboard': inline_keyboard}
                )
                logger.info(f"Alerta de teste vencendo enviado para {nome} (ID: {chat_id})")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de teste vencendo: {e}")

    def _enviar_alerta_renovacao(self, usuario):
        try:
            chat_id = usuario.get('chat_id')
            nome = usuario.get('nome', 'usuário')
            vencimento = usuario.get('proximo_vencimento')
            if isinstance(vencimento, datetime):
                data_vencimento = vencimento.strftime('%d/%m/%Y')
            else:
                data_vencimento = 'amanhã'
            mensagem = f"""🔄 *RENOVAÇÃO DE PLANO*

Olá {nome}! 👋

Seu plano mensal vence *{data_vencimento}*.

Para manter o acesso ao sistema sem interrupções, renove seu plano agora!

💡 *Renovação:* R$ 20,00 por mais 30 dias
✅ *Sem perda de dados ou configurações*
📱 *Continuidade total do serviço*
🚀 *Sempre com as últimas atualizações*

Renove agora e mantenha tudo funcionando! 👇"""
            inline_keyboard = [
                [
                    {'text': '🔄 Renovar - Gerar PIX R$ 20,00', 'callback_data': f'gerar_pix_renovacao_{chat_id}'},
                ],
                [
                    {'text': '📞 Falar com Suporte', 'url': 'https://t.me/seu_suporte'},
                    {'text': '📋 Minha Conta', 'callback_data': 'minha_conta'}
                ]
            ]
            if hasattr(self, 'bot') and self.bot:
                self.bot.send_message(
                    chat_id,
                    mensagem,
                    parse_mode='Markdown',
                    reply_markup={'inline_keyboard': inline_keyboard}
                )
                logger.info(f"Alerta de renovação enviado para {nome} (ID: {chat_id})")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de renovação: {e}")

    def set_bot_instance(self, bot_instance):
        """Define a instância do bot para envio de mensagens"""
        self.bot = bot_instance

    # ===================== Utilidades de Log / Duplicidade =====================
    def _ja_enviada_hoje(self, cliente_id, template_id):
        """Verifica se a mensagem já foi enviada hoje para evitar duplicatas"""
        try:
            hoje = agora_br().date()
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM logs_envio 
                        WHERE cliente_id = %s 
                          AND template_id = %s
                          AND DATE(data_envio) = %s 
                          AND sucesso = TRUE
                        """,
                        (cliente_id, template_id, hoje)
                    )
                    count = cursor.fetchone()[0]
                    return count > 0
        except Exception as e:
            logger.error(f"Erro ao verificar duplicata: {e}")
            return False

    # ===================== API pública de agendamento =====================
    def agendar_mensagens_cliente(self, cliente_id):
        """Agenda mensagens para um cliente específico (usado no cadastro)"""
        try:
            cliente = self.db.buscar_cliente_por_id(cliente_id)
            if not cliente:
                return
            threading.Thread(
                target=self._agendar_mensagens_cliente_sync,
                args=(cliente,),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Erro ao agendar mensagens para cliente {cliente_id}: {e}")

    def _agendar_mensagens_cliente_sync(self, cliente):
        """Agenda apenas mensagem de boas-vindas para novo cliente"""
        try:
            template_boas_vindas = self.db.obter_template_por_tipo('boas_vindas', cliente.get('chat_id_usuario'))
            if template_boas_vindas:
                mensagem_boas_vindas = self.template_manager.processar_template(
                    template_boas_vindas['conteudo'], cliente
                )
                agendado_para = agora_br() + timedelta(minutes=5)  # tz-aware
                self.db.adicionar_fila_mensagem(
                    cliente_id=cliente['id'],
                    template_id=template_boas_vindas['id'],
                    telefone=cliente['telefone'],
                    mensagem=mensagem_boas_vindas,
                    tipo_mensagem='boas_vindas',
                    agendado_para=agendado_para
                )
                logger.info(f"Mensagem de boas vindas agendada para novo cliente: {cliente['nome']}")
        except Exception as e:
            logger.error(f"Erro ao agendar mensagens para cliente: {e}")

    def agendar_mensagem_personalizada(self, cliente_id, template_id, data_hora):
        """Agenda mensagem personalizada (espera data_hora tz-aware)"""
        try:
            cliente = self.db.buscar_cliente_por_id(cliente_id)
            template = self.db.obter_template(template_id)
            if not cliente or not template:
                return False
            mensagem = self.template_manager.processar_template(template['conteudo'], cliente)
            fila_id = self.db.adicionar_fila_mensagem(
                cliente_id=cliente_id,
                template_id=template_id,
                telefone=cliente['telefone'],
                mensagem=mensagem,
                tipo_mensagem='personalizada',
                agendado_para=data_hora
            )
            logger.info(f"Mensagem personalizada agendada para {cliente['nome']} - ID: {fila_id}")
            return fila_id
        except Exception as e:
            logger.error(f"Erro ao agendar mensagem personalizada: {e}")
            return False

    def reagendar_todas_mensagens(self):
        """Reagenda todas as mensagens baseado nos vencimentos atuais (aplica horário por usuário já hoje)."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM fila_mensagens WHERE processado = FALSE")
                    conn.commit()
            # Recria os agendamentos do dia imediatamente
            self._verificar_e_agendar_mensagens_do_dia()
            logger.info("Reagendamento de todas as mensagens concluído")
            return True
        except Exception as e:
            logger.error(f"Erro ao reagendar mensagens: {e}")
            return False

    # ===================== Projeções / Fila =====================
    def obter_tarefas_pendentes(self):
        """Obtém lista de tarefas pendentes"""
        try:
            mensagens = self.db.obter_mensagens_pendentes(limit=100)
            tarefas = []
            for msg in mensagens:
                tarefas.append({
                    'id': msg['id'],
                    'cliente': msg.get('cliente_nome'),
                    'telefone': msg['telefone'],
                    'tipo': msg['tipo_mensagem'],
                    'agendado_para': msg['agendado_para'],
                    'tentativas': msg.get('tentativas', 0)
                })
            return tarefas
        except Exception as e:
            logger.error(f"Erro ao obter tarefas pendentes: {e}")
            return []

    def obter_proximas_execucoes(self, limit=10):
        """Obtém próximas execuções agendadas"""
        try:
            mensagens = self.db.obter_mensagens_pendentes(limit=limit)
            execucoes = []
            for msg in mensagens:
                execucoes.append({
                    'data': formatar_datetime_br(msg['agendado_para']),
                    'tipo': msg['tipo_mensagem'],
                    'cliente': msg.get('cliente_nome'),
                    'telefone': msg['telefone']
                })
            return execucoes
        except Exception as e:
            logger.error(f"Erro ao obter próximas execuções: {e}")
            return []

    def obter_fila_mensagens(self):
        """Obtém fila completa de mensagens"""
        return self.obter_tarefas_pendentes()

    # ===================== Config helpers =====================
    def _get_horario_config_global(self, chave, default='09:00'):
        """Obtém horário configurado GLOBAL do banco ou usa padrão"""
        try:
            config = self.db.obter_configuracao(chave, chat_id_usuario=None)
            if config:
                return config
        except Exception as e:
            logger.warning(f"Erro ao carregar configuração global {chave}: {e}")
        return default

    def _get_horario_config_usuario(self, chave, chat_id_usuario, default='09:00'):
        """Obtém horário configurado POR USUÁRIO ou usa global como fallback"""
        try:
            config = self.db.obter_configuracao(chave, chat_id_usuario=chat_id_usuario)
            if config:
                return config
            config = self.db.obter_configuracao(chave, chat_id_usuario=None)
            if config:
                return config
        except Exception as e:
            logger.warning(f"Erro ao carregar configuração {chave} para usuário {chat_id_usuario}: {e}")
        return default

    # ===================== Debug =====================
    def debug_timezone(self):
        try:
            logger.info(f"TZ do scheduler: {self.scheduler.timezone}")
            logger.info(f"agora_br(): {agora_br().isoformat()}")
            for job in self.scheduler.get_jobs():
                logger.info(f"JOB {job.id} -> next: {job.next_run_time}")
        except Exception as e:
            logger.error(f"Erro no debug de timezone: {e}")

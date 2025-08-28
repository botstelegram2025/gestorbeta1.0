"""
Sistema de Agendamento de Mensagens (versão funcional c/ bootstrap + backfill)
- Respeita horários definidos por USUÁRIO (fallback global)
- Fila do dia: criada às 05:00 + no bootstrap de inicialização + backfill periódico
- Worker minutal envia quando chegar o horário (America/Sao_Paulo)
- Jobs principais: verificação 05:00, backfill 30/30 min, limpeza, worker minutal
"""

import logging
import threading
from datetime import datetime, timedelta, time as dtime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import pytz
import time as _time

from utils import agora_br, formatar_datetime_br  # garanta tz-aware em agora_br()

logger = logging.getLogger(__name__)


class MessageScheduler:
    def __init__(self, database_manager, baileys_api, template_manager):
        """Inicializa o agendador de mensagens"""
        self.db = database_manager
        self.baileys_api = baileys_api
        self.template_manager = template_manager

        # Scheduler com timezone fixo de SP e defaults seguros
        self.scheduler = BackgroundScheduler(
            timezone=pytz.timezone('America/Sao_Paulo'),
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300  # 5 min
            }
        )
        self.tz = self.scheduler.timezone
        self.running = False
        self.ultima_verificacao_time = None
        self.bot = None  # pode ser setado via set_bot_instance

        # Configura jobs principais
        self._setup_main_jobs()

    # ===================== Helpers de timezone =====================
    def _ensure_aware(self, dt):
        """Converte datetime (ou string) para tz-aware em America/Sao_Paulo."""
        if dt is None:
            return None
        try:
            # Se vier string do banco (ISO etc.)
            if isinstance(dt, str):
                # Tenta ISO first; aceita 'Z' como UTC
                s = dt.replace('Z', '+00:00') if 'Z' in dt and '+' not in dt else dt
                parsed = datetime.fromisoformat(s)
                dt = parsed
        except Exception:
            # Último recurso: ignora parsing e trata abaixo como naive
            pass

        # Se ainda não é datetime, não há o que normalizar
        if not isinstance(dt, datetime):
            return dt

        # Já é tz-aware
        if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
            return dt.astimezone(self.tz)

        # É naive -> localiza em SP
        try:
            return self.tz.localize(dt)
        except Exception:
            # fallback: assume como "horário local" de SP
            return dt.replace(tzinfo=self.tz)

    # ===================== Setup de Jobs =====================
    def _setup_main_jobs(self):
        """Configura os jobs principais do sistema"""
        try:
            horario_envio = self._get_horario_config_global('horario_envio', '09:00')
            horario_verificacao = self._get_horario_config_global('horario_verificacao', '09:00')
            horario_limpeza = self._get_horario_config_global('horario_limpeza', '02:00')

            logger.info(
                f"Sistema usando horários globais (para jobs não-atômicos): "
                f"Verificação {horario_verificacao}, Limpeza {horario_limpeza}"
            )
            logger.info("Envios aos clientes são agendados por usuário (HH:MM individual)")

            # Parse seguro
            try:
                _ = list(map(int, horario_envio.split(':')))     # validação
                hora_verif, min_verif = map(int, horario_verificacao.split(':'))
                hora_limp, min_limp = map(int, horario_limpeza.split(':'))
            except ValueError as e:
                logger.error(f"Erro no formato dos horários globais: {e}")
                hora_verif, min_verif = 9, 0
                hora_limp, min_limp = 2, 0

            # Limpa jobs antigos por id
            for job_id in [
                'envio_diario_9h',          # legado: não usamos mais
                'limpar_fila',
                'alertas_usuarios',
                'verificacao_5h',
                'verificacao_backfill',
                'verificacao_bootstrap',
                'processar_fila_minuto'
            ]:
                try:
                    job = self.scheduler.get_job(job_id)
                    if job:
                        self.scheduler.remove_job(job_id)
                except Exception:
                    pass

            # Limpeza
            self.scheduler.add_job(
                func=self._limpar_fila_antiga,
                trigger=CronTrigger(hour=hora_limp, minute=min_limp, timezone=self.scheduler.timezone),
                id='limpar_fila',
                name=f'Limpar Fila Antiga às {hora_limp:02d}:{min_limp:02d}',
                replace_existing=True
            )

            # Alertas diários (por usuário)
            self.scheduler.add_job(
                func=self._enviar_alertas_usuarios,
                trigger=CronTrigger(hour=hora_verif, minute=min_verif, timezone=self.scheduler.timezone),
                id='alertas_usuarios',
                name=f'Alertas Diários por Usuário às {hora_verif:02d}:{min_verif:02d}',
                replace_existing=True
            )

            # Verificação diária às 05:00 (monta fila do dia)
            self.scheduler.add_job(
                func=self._verificar_e_agendar_mensagens_do_dia,
                trigger=CronTrigger(hour=5, minute=0, timezone=self.scheduler.timezone),
                id='verificacao_5h',
                name='Verificação diária às 05:00',
                replace_existing=True
            )

            # Backfill periódico (a cada 30 minutos): garante fila caso tenha havido queda/restart
            self.scheduler.add_job(
                func=self._verificar_e_agendar_mensagens_do_dia,
                trigger=CronTrigger(minute='*/30', timezone=self.scheduler.timezone),
                id='verificacao_backfill',
                name='Backfill de verificação (*/30 min)',
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=600
            )

            # Worker da fila: roda todo minuto no segundo 0
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
            logger.info(
                f"Jobs principais configurados. "
                f"Verificação: {hora_verif:02d}:{min_verif:02d}, "
                f"Limpeza: {hora_limp:02d}:{min_limp:02d} | Total: {jobs_count}"
            )

        except Exception as e:
            logger.error(f"Erro ao configurar jobs principais: {e}")
            raise

    # ===================== Controle do Scheduler =====================
    def start(self):
        """Inicia o agendador, agenda bootstrap imediato e exibe diagnóstico"""
        try:
            if self.running and self.scheduler.running:
                logger.info("Agendador já está em execução")
                return

            self.scheduler.start()
            self.running = True
            logger.info("Agendador de mensagens iniciado com sucesso!")

            # Bootstrap: monta a fila do dia na inicialização (em ~3s)
            run_at = self._ensure_aware(agora_br() + timedelta(seconds=3))
            try:
                self.scheduler.add_job(
                    func=self._verificar_e_agendar_mensagens_do_dia,
                    trigger=DateTrigger(run_date=run_at),
                    id='verificacao_bootstrap',
                    name='Bootstrap: montar fila do dia na inicialização',
                    replace_existing=True,
                )
                logger.info("Bootstrap de verificação agendado para agora (+3s).")
            except Exception as e:
                logger.warning(f"Falha ao agendar bootstrap: {e}. Rodando diretamente agora.")
                # fallback: roda imediato
                self._verificar_e_agendar_mensagens_do_dia()

            # Log de diagnóstico
            self.debug_timezone()

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

            mensagens_pendentes = self.db.obter_mensagens_pendentes(limit=100) or []

            if not mensagens_pendentes:
                logger.info("Nenhuma mensagem pendente para processamento")
                return

            logger.info(f"Encontradas {len(mensagens_pendentes)} mensagens pendentes")
            # Debug: mostra 5 próximas
            for preview in mensagens_pendentes[:5]:
                logger.info(
                    f"[Fila] id={preview.get('id')} cliente={preview.get('cliente_nome')} "
                    f"tipo={preview.get('tipo_mensagem')} agendado_para={preview.get('agendado_para')}"
                )

            agora = agora_br()
            for mensagem in mensagens_pendentes:
                try:
                    ag = self._ensure_aware(mensagem.get('agendado_para'))
                    # Se veio sem agendamento, envia imediatamente
                    if ag is None or ag <= agora:
                        self._enviar_mensagem_fila(mensagem)
                        _time.sleep(1.5)  # polidez com a API
                    else:
                        # Ainda não é hora
                        continue
                except Exception as e:
                    logger.error(f"Erro ao processar mensagem ID {mensagem.get('id')}: {e}")
                    try:
                        self.db.marcar_mensagem_processada(mensagem['id'], False, str(e))
                    except Exception:
                        pass

            logger.info("Processamento da fila concluído")

        except Exception as e:
            logger.error(f"Erro no processamento da fila: {e}")

    def _enviar_mensagem_fila(self, mensagem):
        """Envia uma mensagem da fila"""
        try:
            # Verificar se cliente ainda está ativo
            cliente = self.db.buscar_cliente_por_id(mensagem['cliente_id'])
            if not cliente or not cliente.get('ativo', True):
                logger.info(f"Cliente {mensagem['cliente_id']} inativo, removendo da fila")
                self.db.marcar_mensagem_processada(mensagem['id'], True, "cliente_inativo")
                return

            chat_id_usuario = (
                mensagem.get('chat_id_usuario')
                or cliente.get('chat_id_usuario')
            )
            if not chat_id_usuario:
                logger.error(f"Mensagem ID {mensagem['id']} sem chat_id_usuario - não pode enviar WhatsApp")
                self.db.marcar_mensagem_processada(mensagem['id'], False, "chat_id_usuario ausente")
                return

            resultado = self.baileys_api.send_message(
                phone=mensagem['telefone'],
                message=mensagem['mensagem'],
                chat_id_usuario=chat_id_usuario
            )

            if resultado and resultado.get('success'):
                # Registrar envio OK
                self.db.registrar_envio(
                    cliente_id=mensagem['cliente_id'],
                    template_id=mensagem['template_id'],
                    telefone=mensagem['telefone'],
                    mensagem=mensagem['mensagem'],
                    tipo_envio='automatico',
                    sucesso=True,
                    message_id=resultado.get('message_id'),
                    chat_id_usuario=chat_id_usuario
                )
                # Marcar processado
                self.db.marcar_mensagem_processada(mensagem['id'], True, "enviado")
                logger.info(
                    f"Mensagem enviada: {mensagem.get('cliente_nome')} ({mensagem['telefone']}) | "
                    f"tipo={mensagem.get('tipo_mensagem')}"
                )
            else:
                erro = (resultado or {}).get('error', 'Erro desconhecido')
                self.db.registrar_envio(
                    cliente_id=mensagem['cliente_id'],
                    template_id=mensagem['template_id'],
                    telefone=mensagem['telefone'],
                    mensagem=mensagem['mensagem'],
                    tipo_envio='automatico',
                    sucesso=False,
                    erro=erro,
                    chat_id_usuario=chat_id_usuario
                )
                self.db.marcar_mensagem_processada(mensagem['id'], False, erro)
                logger.error(f"Falha ao enviar mensagem para {mensagem.get('cliente_nome')}: {erro}")

        except Exception as e:
            logger.error(f"Erro ao enviar mensagem da fila: {e}")
            try:
                self.db.marcar_mensagem_processada(mensagem['id'], False, str(e))
            except Exception:
                pass

    # ===================== Envio diário por usuário (LEGADO/Manual) =====================
    def _processar_envio_diario_9h(self):
        """Mantido para compatibilidade/uso manual. NÃO é agendado automaticamente."""
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
            horario_usuario = self._get_horario_config_usuario('horario_envio', chat_id_usuario, None)
            if horario_usuario:
                hora_atual = agora_br().strftime('%H:%M')
                if horario_usuario != hora_atual[:5]:
                    logger.info(f"Usuário {chat_id_usuario} tem horário {horario_usuario}, mas execução manual agora é {hora_atual}")

            clientes = self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=chat_id_usuario)
            if not clientes:
                logger.debug(f"Usuário {chat_id_usuario}: Nenhum cliente ativo encontrado")
                return 0

            enviadas = 0
            for cliente in clientes:
                try:
                    vencimento = cliente['vencimento']
                    if not hasattr(vencimento, 'toordinal'):  # se não for date/datetime
                        continue
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
                    if not hasattr(vencimento, 'toordinal'):
                        continue
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

            if not self._cliente_pode_receber_mensagem(cliente, tipo_template):
                logger.info(f"Cliente {cliente['nome']} optou por não receber mensagens do tipo {tipo_template}")
                return False

            template = self.db.obter_template_por_tipo(tipo_template, resolved_chat_id)
            if not template:
                logger.warning(f"Template {tipo_template} não encontrado para usuário {resolved_chat_id}")
                return False

            mensagem = self.template_manager.processar_template(template['conteudo'], cliente)

            if self._ja_enviada_hoje(cliente['id'], template['id']):
                logger.info(f"Mensagem {tipo_template} já enviada hoje para {cliente['nome']}")
                return False

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
        """Verifica preferências de notificação por tipo"""
        try:
            cliente_id = cliente['id']
            chat_id_usuario = cliente.get('chat_id_usuario')

            if hasattr(self.db, 'cliente_pode_receber_cobranca'):
                if tipo_template in ['vencimento_1dia_apos', 'vencimento_hoje', 'vencimento_2dias']:
                    return self.db.cliente_pode_receber_cobranca(cliente_id, chat_id_usuario)
                else:
                    return self.db.cliente_pode_receber_notificacoes(cliente_id, chat_id_usuario)
            else:
                logger.warning("Métodos de preferências não disponíveis - permitindo envio")
                return True
        except Exception as e:
            logger.error(f"Erro ao verificar preferências: {e}")
            return True  # falha aberta para não travar operação

    # ===================== Verificação / Agendamento =====================
    def _verificar_e_agendar_mensagens_do_dia(self):
        """Verifica clientes e agenda APENAS mensagens que devem ser enviadas HOJE (no horário do usuário)."""
        try:
            logger.info("=== VERIFICAÇÃO DIÁRIA (fila do dia) ===")
            clientes = self.db.listar_clientes(apenas_ativos=True)
            if not clientes:
                logger.info("Nenhum cliente ativo encontrado")
                return

            contador_agendadas = 0
            hoje = agora_br().date()
            for cliente in clientes:
                try:
                    vencimento = cliente['vencimento']
                    if not hasattr(vencimento, 'toordinal'):
                        continue
                    dias_vencimento = (vencimento - hoje).days

                    if dias_vencimento == -1:
                        self._agendar_mensagem_vencimento(cliente, 'vencimento_1dia_apos', hoje)
                        contador_agendadas += 1
                    elif dias_vencimento == 0:
                        self._agendar_mensagem_vencimento(cliente, 'vencimento_hoje', hoje)
                        contador_agendadas += 1
                    elif dias_vencimento in (1, 2):
                        self._agendar_mensagem_vencimento(cliente, 'vencimento_2dias', hoje)
                        contador_agendadas += 1
                    else:
                        # Ignora >2 dias e <<-1 para agendamento automático diário
                        pass
                except Exception as e:
                    logger.error(f"Erro ao verificar cliente {cliente.get('nome')}: {e}")

            logger.info(f"=== VERIFICAÇÃO CONCLUÍDA: {contador_agendadas} mensagens agendadas para HOJE ===")
        except Exception as e:
            logger.error(f"Erro na verificação diária: {e}")

    def _agendar_mensagem_vencimento(self, cliente, tipo_template, data_envio):
        """Agenda mensagem específica de vencimento para envio no mesmo dia, no HH:MM do USUÁRIO."""
        try:
            template = self.db.obter_template_por_tipo(tipo_template, chat_id_usuario=cliente.get('chat_id_usuario'))
            if not template:
                logger.warning(f"Template {tipo_template} não encontrado (cliente {cliente.get('nome')})")
                return

            mensagem = self.template_manager.processar_template(template['conteudo'], cliente)

            # HH:MM por USUÁRIO com fallback global
            hhmm = self._get_horario_config_usuario(
                'horario_envio',
                cliente.get('chat_id_usuario'),
                default=self._get_horario_config_global('horario_envio', '12:00')
            )
            try:
                h, m = map(int, str(hhmm).split(':'))
            except Exception:
                h, m = 12, 0  # fallback robusto

            alvo = self._ensure_aware(datetime.combine(data_envio, dtime(h, m)))

            # Se já passou do horário do usuário hoje: reprograma para agora + 10min (até 23:59)
            agora = agora_br()
            if alvo <= agora:
                limite_hoje = agora.replace(hour=23, minute=59, second=0, microsecond=0)
                alvo = min(agora + timedelta(minutes=10), limite_hoje)

            # Evitar duplicidade para o mesmo dia
            if self.db.verificar_mensagem_existente(cliente['id'], template['id'], data_envio):
                logger.info(f"Mensagem {tipo_template} já agendada para {cliente['nome']}")
                return

            # Adicionar na fila
            self.db.adicionar_fila_mensagem(
                cliente_id=cliente['id'],
                template_id=template['id'],
                telefone=cliente['telefone'],
                mensagem=mensagem,
                tipo_mensagem=tipo_template,
                agendado_para=alvo,
                chat_id_usuario=cliente.get('chat_id_usuario')
            )

            logger.info(
                f"Agendado {tipo_template} para {cliente['nome']} | "
                f"ENVIO: {alvo.strftime('%d/%m/%Y %H:%M')}"
            )

        except Exception as e:
            logger.error(f"Erro ao agendar mensagem de vencimento: {e}")

    # ===================== Limpeza / Cancelamento =====================
    def _limpar_fila_antiga(self):
        """Remove mensagens antigas processadas da fila e futuras desnecessárias"""
        try:
            logger.info("Iniciando limpeza da fila antiga...")
            removidas_antigas = self.db.limpar_fila_processadas(dias=7)
            removidas_futuras = self.db.limpar_mensagens_futuras()
            logger.info(
                f"Limpeza concluída: {removidas_antigas} mensagens antigas e "
                f"{removidas_futuras} futuras removidas"
            )
        except Exception as e:
            logger.error(f"Erro na limpeza da fila: {e}")

    def cancelar_mensagens_cliente_renovado(self, cliente_id):
        """Cancela todas as mensagens pendentes na fila quando cliente é renovado"""
        try:
            logger.info(f"Cancelando mensagens pendentes para cliente ID: {cliente_id}")
            mensagens_pendentes = self.db.buscar_mensagens_fila_cliente(cliente_id, apenas_pendentes=True) or []
            canceladas = 0
            for mensagem in mensagens_pendentes:
                try:
                    if self.db.cancelar_mensagem_fila(mensagem['id']):
                        canceladas += 1
                        logger.info(f"Mensagem ID {mensagem['id']} cancelada (cliente renovado)")
                except Exception as e:
                    logger.error(f"Erro ao cancelar mensagem ID {mensagem.get('id')}: {e}")
            logger.info(f"Cliente renovado: {canceladas} mensagens canceladas da fila")
            return canceladas
        except Exception as e:
            logger.error(f"Erro ao cancelar mensagens de cliente renovado: {e}")
            return 0

    # ===================== Alertas (admin/usuário) =====================
    def _enviar_alertas_usuarios(self):
        """Envia alerta diário isolado para cada usuário e dispara alertas do sistema."""
        try:
            import os
            logger.info("Enviando alertas diários por usuário...")

            # Alertas do sistema (teste/renovação) para amanhã
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
        """Alerta individual para um usuário específico"""
        try:
            import os
            logger.info(f"Enviando alerta diário para usuário {chat_id_usuario}...")

            horario_alerta_usuario = self._get_horario_config_usuario('horario_verificacao', chat_id_usuario, None)
            if horario_alerta_usuario:
                hora_atual = agora_br().strftime('%H:%M')
                if horario_alerta_usuario != hora_atual[:5]:
                    logger.info(
                        f"Usuário {chat_id_usuario} prefere alertas às {horario_alerta_usuario}, "
                        f"mas execução é no horário global"
                    )

            hoje = agora_br().date()
            clientes_hoje, clientes_proximos, clientes_vencidos = [], [], []
            clientes = self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=chat_id_usuario) or []
            for cliente in clientes:
                try:
                    vencimento = cliente['vencimento']
                    if not hasattr(vencimento, 'toordinal'):
                        continue
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
                    for c in clientes_vencidos[:5]:
                        dias_vencido = abs((c['vencimento'] - hoje).days)
                        mensagem += f"• {c['nome']} - há {dias_vencido} dias\n"
                    if len(clientes_vencidos) > 5:
                        mensagem += f"• +{len(clientes_vencidos) - 5} outros vencidos\n\n"
                    else:
                        mensagem += "\n"

                if clientes_hoje:
                    mensagem += f"⚠️ *VENCEM HOJE ({len(clientes_hoje)}):*\n"
                    for c in clientes_hoje:
                        try:
                            mensagem += f"• {c['nome']} - R$ {c['valor']:.2f}\n"
                        except Exception:
                            mensagem += f"• {c['nome']}\n"
                    mensagem += "\n"

                if clientes_proximos:
                    mensagem += f"📅 *PRÓXIMOS 7 DIAS ({len(clientes_proximos)}):*\n"
                    for c in clientes_proximos[:5]:
                        dias_restantes = (c['vencimento'] - hoje).days
                        mensagem += f"• {c['nome']} - {dias_restantes} dias\n"
                    if len(clientes_proximos) > 5:
                        mensagem += f"• +{len(clientes_proximos) - 5} outros próximos\n"
                    mensagem += "\n"

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

            logger.info("Alerta diário enviado (admin)")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta diário: {e}")

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
            data = {'chat_id': admin_chat_id, 'text': mensagem, 'parse_mode': 'Markdown'}
            response = requests.post(url, data=data, timeout=10)

            if response.status_code == 200:
                logger.info("Alerta enviado com sucesso para administrador")
            else:
                logger.error(f"Erro ao enviar alerta: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para admin: {e}")

    # ===================== Usuários do sistema (teste/renovação) =====================
    def _verificar_usuarios_sistema(self, data_vencimento):
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
                for usuario in cursor.fetchall() or []:
                    self._enviar_alerta_teste_vencendo(dict(usuario))
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
                for usuario in cursor.fetchall() or []:
                    self._enviar_alerta_renovacao(dict(usuario))
        except Exception as e:
            logger.error(f"Erro ao verificar usuários pagos vencendo: {e}")

    def _enviar_alerta_teste_vencendo(self, usuario):
        # (sem alterações substanciais)
        try:
            chat_id = usuario.get('chat_id')
            nome = usuario.get('nome', 'usuário')
            fim_teste = usuario.get('fim_periodo_teste')
            data_vencimento = fim_teste.strftime('%d/%m/%Y') if isinstance(fim_teste, datetime) else 'amanhã'
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
                [{'text': '💳 Gerar PIX - R$ 20,00', 'callback_data': f'gerar_pix_usuario_{chat_id}'}],
                [{'text': '📞 Falar com Suporte', 'url': 'https://t.me/seu_suporte'},
                 {'text': '❓ Dúvidas', 'callback_data': 'info_planos'}]
            ]
            if self.bot:
                self.bot.send_message(
                    chat_id, mensagem, parse_mode='Markdown',
                    reply_markup={'inline_keyboard': inline_keyboard}
                )
                logger.info(f"Alerta de teste vencendo enviado para {nome} (ID: {chat_id})")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de teste vencendo: {e}")

    def _enviar_alerta_renovacao(self, usuario):
        # (sem alterações substanciais)
        try:
            chat_id = usuario.get('chat_id')
            nome = usuario.get('nome', 'usuário')
            vencimento = usuario.get('proximo_vencimento')
            data_vencimento = vencimento.strftime('%d/%m/%Y') if isinstance(vencimento, datetime) else 'amanhã'
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
                [{'text': '🔄 Renovar - Gerar PIX R$ 20,00', 'callback_data': f'gerar_pix_renovacao_{chat_id}'}],
                [{'text': '📞 Falar com Suporte', 'url': 'https://t.me/seu_suporte'},
                 {'text': '📋 Minha Conta', 'callback_data': 'minha_conta'}]
            ]
            if self.bot:
                self.bot.send_message(
                    chat_id, mensagem, parse_mode='Markdown',
                    reply_markup={'inline_keyboard': inline_keyboard}
                )
                logger.info(f"Alerta de renovação enviado para {nome} (ID: {chat_id})")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de renovação: {e}")

    def set_bot_instance(self, bot_instance):
        """Define a instância do bot para envio de mensagens"""
        self.bot = bot_instance

    # ===================== Logs / Duplicidade =====================
    def _ja_enviada_hoje(self, cliente_id, template_id):
        """Verifica se a mensagem já foi enviada hoje para evitar duplicatas"""
        try:
            hoje = agora_br().date()
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM logs_envio 
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
                mensagem = self.template_manager.processar_template(template_boas_vindas['conteudo'], cliente)
                agendado_para = self._ensure_aware(agora_br() + timedelta(minutes=5))
                self.db.adicionar_fila_mensagem(
                    cliente_id=cliente['id'],
                    template_id=template_boas_vindas['id'],
                    telefone=cliente['telefone'],
                    mensagem=mensagem,
                    tipo_mensagem='boas_vindas',
                    agendado_para=agendado_para,
                    chat_id_usuario=cliente.get('chat_id_usuario')
                )
                logger.info(f"Mensagem de boas-vindas agendada para novo cliente: {cliente['nome']}")
        except Exception as e:
            logger.error(f"Erro ao agendar mensagens para cliente: {e}")

    def agendar_mensagem_personalizada(self, cliente_id, template_id, data_hora):
        """Agenda mensagem personalizada (espera data_hora tz-aware, mas normaliza por garantia)"""
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
                agendado_para=self._ensure_aware(data_hora),
                chat_id_usuario=cliente.get('chat_id_usuario')
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
            mensagens = self.db.obter_mensagens_pendentes(limit=100) or []
            tarefas = []
            for msg in mensagens:
                tarefas.append({
                    'id': msg.get('id'),
                    'cliente': msg.get('cliente_nome'),
                    'telefone': msg.get('telefone'),
                    'tipo': msg.get('tipo_mensagem'),
                    'agendado_para': self._ensure_aware(msg.get('agendado_para')),
                    'tentativas': msg.get('tentativas', 0)
                })
            return tarefas
        except Exception as e:
            logger.error(f"Erro ao obter tarefas pendentes: {e}")
            return []

    def obter_proximas_execucoes(self, limit=10):
        """Obtém próximas execuções agendadas (dados da fila)"""
        try:
            mensagens = self.db.obter_mensagens_pendentes(limit=limit) or []
            execucoes = []
            for msg in mensagens:
                execucoes.append({
                    'data': formatar_datetime_br(self._ensure_aware(msg.get('agendado_para'))),
                    'tipo': msg.get('tipo_mensagem'),
                    'cliente': msg.get('cliente_nome'),
                    'telefone': msg.get('telefone')
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
        """Obtém horário GLOBAL do banco ou usa padrão"""
        try:
            config = self.db.obter_configuracao(chave, chat_id_usuario=None)
            if config:
                return config
        except Exception as e:
            logger.warning(f"Erro ao carregar configuração global {chave}: {e}")
        return default

    def _get_horario_config_usuario(self, chave, chat_id_usuario, default='09:00'):
        """Obtém horário POR USUÁRIO ou usa global como fallback"""
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

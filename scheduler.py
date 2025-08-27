"""
Sistema de Agendamento de Mensagens
Gerencia envios automáticos baseados em vencimentos e agenda mensagens personalizadas
"""

import logging
import threading
import time
from datetime import datetime, timedelta, time as dtime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_RUNNING
from apscheduler.triggers.cron import CronTrigger

from utils import agora_br, formatar_data_br, formatar_datetime_br

logger = logging.getLogger(__name__)


class MessageScheduler:
    """Orquestra o agendamento, verificação e envio de mensagens.

    Observações importantes:
    - Todos os horários usam America/Sao_Paulo (timezone-aware)
    - Ao iniciar, executa um *catch-up* da verificação das 05:00 caso o processo
      tenha reiniciado depois desse horário.
    - Fila processada a cada minuto (segundo 0) com tolerância de misfire ampliada.
    """

    def __init__(self, database_manager, baileys_api, template_manager):
        self.db = database_manager
        self.baileys_api = baileys_api
        self.template_manager = template_manager

        self.tz = pytz.timezone("America/Sao_Paulo")

        # BackgroundScheduler: compatível com threading
        self.scheduler = BackgroundScheduler(
            timezone=self.tz,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,  # 5 minutos de tolerância por padrão
            },
        )
        self.running = False
        self.ultima_verificacao_time = None
        self.bot = None  # opcional: instância do seu bot Telegram

        self._setup_main_jobs()

    # ------------------------------------------------------------------
    # Setup / lifecycle
    # ------------------------------------------------------------------
    def _setup_main_jobs(self):
        """Configura os jobs principais do sistema."""
        try:
            horario_envio = self._get_horario_config_global("horario_envio", "09:00")
            horario_verificacao = self._get_horario_config_global("horario_verificacao", "09:00")
            horario_limpeza = self._get_horario_config_global("horario_limpeza", "02:00")

            logger.info(
                f"Sistema usando horários globais: Envio {horario_envio}, Verificação {horario_verificacao}, Limpeza {horario_limpeza}"
            )
            logger.info(
                "Preferências individuais de horário são detectadas, mas a execução é centralizada para eficiência"
            )

            # Parse/validação dos horários
            try:
                hora_envio, min_envio = map(int, horario_envio.split(":"))
                hora_verif, min_verif = map(int, horario_verificacao.split(":"))
                hora_limp, min_limp = map(int, horario_limpeza.split(":"))
            except ValueError as e:
                logger.error(f"Erro no formato dos horários: {e}")
                hora_envio, min_envio = 9, 0
                hora_verif, min_verif = 9, 0
                hora_limp, min_limp = 2, 0

            # Limpa jobs existentes
            for job_id in [
                "envio_diario_9h",
                "limpar_fila",
                "alertas_usuarios",
                "verificacao_5h",
                "processar_fila_minuto",
            ]:
                try:
                    if self.scheduler.get_job(job_id):
                        self.scheduler.remove_job(job_id)
                except Exception:
                    pass

            # Envio diário no horário configurado
            self.scheduler.add_job(
                func=self._processar_envio_diario_9h,
                trigger=CronTrigger(hour=hora_envio, minute=min_envio, timezone=self.scheduler.timezone),
                id="envio_diario_9h",
                name=f"Envio Diário às {horario_envio}",
                replace_existing=True,
            )

            # Limpeza da fila
            self.scheduler.add_job(
                func=self._limpar_fila_antiga,
                trigger=CronTrigger(hour=hora_limp, minute=min_limp, timezone=self.scheduler.timezone),
                id="limpar_fila",
                name=f"Limpar Fila Antiga às {horario_limpeza}",
                replace_existing=True,
            )

            # Alertas diários por usuário
            self.scheduler.add_job(
                func=self._enviar_alertas_usuarios,
                trigger=CronTrigger(hour=hora_verif, minute=min_verif, timezone=self.scheduler.timezone),
                id="alertas_usuarios",
                name=f"Alertas Diários por Usuário às {horario_verificacao}",
                replace_existing=True,
            )

            # Verificação diária às 05:00 para montar a fila do dia
            self.scheduler.add_job(
                func=self._verificar_e_agendar_mensagens_do_dia,
                trigger=CronTrigger(hour=5, minute=0, timezone=self.scheduler.timezone),
                id="verificacao_5h",
                name="Verificação diária às 05:00",
                replace_existing=True,
            )

            # Worker da fila: roda a cada minuto (segundo 0)
            self.scheduler.add_job(
                func=self._processar_fila_mensagens,
                trigger=CronTrigger(second=0, timezone=self.scheduler.timezone),
                id="processar_fila_minuto",
                name="Processar fila (minutal)",
                replace_existing=True,
                misfire_grace_time=300,  # ↑ tolerância extra porque o loop pode durar
                coalesce=True,
            )

            logger.info(
                f"Jobs principais configurados - Envio: {horario_envio}, Verificação: {horario_verificacao}, Limpeza: {horario_limpeza}"
            )

            # Log das próximas execuções
            for job in self.scheduler.get_jobs():
                logger.info(
                    f"JOB {job.id} -> próxima execução: {formatar_datetime_br(job.next_run_time.astimezone(self.tz)) if job.next_run_time else 'N/A'}"
                )

        except Exception as e:
            logger.error(f"Erro ao configurar jobs principais: {e}")
            raise

    def start(self):
        """Inicia o agendador e faz catch-up da verificação do dia."""
        try:
            if not self.running:
                self.scheduler.start()
                self.running = True
                logger.info("Agendador de mensagens iniciado com sucesso!")
                horario_envio = self._get_horario_config_global("horario_envio", "09:00")
                logger.info(f"Mensagens serão enviadas diariamente às {horario_envio}")

                # Catch-up: se já passou das 05:00 no dia atual, execute a verificação uma vez
                agora = agora_br()
                if agora.hour >= 5:
                    logger.info("Executando verificação do dia (catch-up pós-reinício)...")
                    self._verificar_e_agendar_mensagens_do_dia()

                # Logar again next_run_time após catch-up
                for job in self.scheduler.get_jobs():
                    logger.info(
                        f"JOB {job.id} -> próxima execução: {formatar_datetime_br(job.next_run_time.astimezone(self.tz)) if job.next_run_time else 'N/A'}"
                    )
        except Exception as e:
            logger.error(f"Erro ao iniciar agendador: {e}")

    def stop(self):
        """Para o agendador."""
        try:
            if self.running:
                self.scheduler.shutdown()
                self.running = False
                logger.info("Agendador de mensagens parado")
        except Exception as e:
            logger.error(f"Erro ao parar agendador: {e}")

    def is_running(self):
        """Verifica se o agendador está rodando."""
        try:
            return self.running and self.scheduler.state == STATE_RUNNING
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _as_aware(self, dt: datetime | None) -> datetime | None:
        """Garante que o datetime seja timezone-aware em America/Sao_Paulo."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return self.tz.localize(dt)
        return dt.astimezone(self.tz)

    def ultima_verificacao(self):
        """Retorna a última verificação formatada."""
        if self.ultima_verificacao_time:
            return formatar_datetime_br(self.ultima_verificacao_time)
        return "Nunca executado"

    def set_bot_instance(self, bot_instance):
        """Define a instância do bot para envio de mensagens (opcional)."""
        self.bot = bot_instance

    # ------------------------------------------------------------------
    # Worker da fila
    # ------------------------------------------------------------------
    def _processar_fila_mensagens(self):
        """Processa mensagens pendentes na fila."""
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
                    ag = self._as_aware(mensagem.get("agendado_para"))
                    agora = agora_br()
                    if ag and ag > agora:
                        # ainda não é hora
                        continue

                    self._enviar_mensagem_fila(mensagem)
                    time.sleep(1)  # pequena pausa para não saturar a API do WhatsApp
                except Exception as e:
                    logger.error(f"Erro ao processar mensagem ID {mensagem['id']}: {e}")
                    self.db.marcar_mensagem_processada(mensagem["id"], False, str(e))

            logger.info("Processamento da fila concluído")

        except Exception as e:
            logger.error(f"Erro no processamento da fila: {e}")

    def _enviar_mensagem_fila(self, mensagem):
        """Envia uma mensagem retirada da fila."""
        try:
            # Verificar se cliente ainda está ativo
            cliente = self.db.buscar_cliente_por_id(mensagem["cliente_id"])
            if not cliente or not cliente.get("ativo", True):
                logger.info(
                    f"Cliente {mensagem['cliente_id']} inativo, removendo da fila"
                )
                self.db.marcar_mensagem_processada(mensagem["id"], True)
                return

            # Enviar mensagem via Baileys - incluir chat_id_usuario obrigatório
            chat_id_usuario = mensagem.get("chat_id_usuario") or cliente.get(
                "chat_id_usuario"
            )
            if not chat_id_usuario:
                logger.error(
                    f"Mensagem ID {mensagem['id']} sem chat_id_usuario - não pode enviar WhatsApp"
                )
                self.db.marcar_mensagem_processada(
                    mensagem["id"], False, "chat_id_usuario não encontrado"
                )
                return

            resultado = self.baileys_api.send_message(
                phone=mensagem["telefone"],
                message=mensagem["mensagem"],
                chat_id_usuario=chat_id_usuario,
            )

            sucesso = bool(resultado and resultado.get("success"))

            if sucesso:
                # Registrar envio bem-sucedido
                self.db.registrar_envio(
                    cliente_id=mensagem["cliente_id"],
                    template_id=mensagem["template_id"],
                    telefone=mensagem["telefone"],
                    mensagem=mensagem["mensagem"],
                    tipo_envio="automatico",
                    sucesso=True,
                    message_id=(resultado or {}).get("message_id"),
                )

                # Marcar como processado
                self.db.marcar_mensagem_processada(mensagem["id"], True)

                logger.info(
                    f"Mensagem enviada com sucesso para {mensagem['cliente_nome']} ({mensagem['telefone']})"
                )

            else:
                # Registrar falha
                erro = (resultado or {}).get("error", "Erro desconhecido")

                self.db.registrar_envio(
                    cliente_id=mensagem["cliente_id"],
                    template_id=mensagem["template_id"],
                    telefone=mensagem["telefone"],
                    mensagem=mensagem["mensagem"],
                    tipo_envio="automatico",
                    sucesso=False,
                    erro=erro,
                )

                # Incrementar tentativas / marcar como não processado
                self.db.marcar_mensagem_processada(mensagem["id"], False, erro)

                logger.error(
                    f"Falha ao enviar mensagem para {mensagem['cliente_nome']}: {erro}"
                )

        except Exception as e:
            logger.error(f"Erro ao enviar mensagem da fila: {e}")
            try:
                self.db.marcar_mensagem_processada(mensagem["id"], False, str(e))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Envio diário às 9h
    # ------------------------------------------------------------------
    def _processar_envio_diario_9h(self):
        """Processa e envia todas as mensagens necessárias às 9h da manhã."""
        try:
            logger.info("=== ENVIO DIÁRIO ÀS 9H DA MANHÃ ===")
            logger.info("Processando e enviando mensagens POR USUÁRIO...")

            hoje = agora_br().date()
            amanha = hoje + timedelta(days=1)

            # Alertas do próprio sistema (teste/renovação de usuários do app)
            self._verificar_usuarios_sistema(amanha)

            # Processar clientes por usuário
            usuarios_ativos = self._obter_usuarios_ativos()
            if not usuarios_ativos:
                logger.info("Nenhum usuário ativo encontrado para processamento")
                return

            logger.info(
                f"Processando clientes de {len(usuarios_ativos)} usuários ativos"
            )

            enviadas_total = 0
            for usuario in usuarios_ativos:
                chat_id_usuario = usuario["chat_id"]
                enviadas_usuario = self._processar_clientes_usuario(chat_id_usuario, hoje)
                enviadas_total += enviadas_usuario
                logger.info(
                    f"Usuário {chat_id_usuario}: {enviadas_usuario} mensagens enviadas"
                )

            logger.info(
                f"=== ENVIO CONCLUÍDO: {enviadas_total} mensagens enviadas às 9h ==="
            )

        except Exception as e:
            logger.error(f"Erro no envio diário às 9h: {e}")

    def _obter_usuarios_ativos(self):
        """Obtém lista de usuários ativos do sistema."""
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
        """Processa clientes de um usuário específico no contexto do envio das 9h."""
        try:
            # Loga preferência de horário do usuário (execução continua no horário global)
            horario_usuario = self._get_horario_config_usuario(
                "horario_envio", chat_id_usuario, None
            )
            if horario_usuario:
                hora_atual = agora_br().strftime("%H:%M")
                if horario_usuario != hora_atual[:5]:
                    logger.info(
                        f"Usuário {chat_id_usuario} tem horário preferido {horario_usuario}, executando no horário global"
                    )

            clientes = self.db.listar_clientes(
                apenas_ativos=True, chat_id_usuario=chat_id_usuario
            )
            if not clientes:
                logger.debug(f"Usuário {chat_id_usuario}: Nenhum cliente ativo encontrado")
                return 0

            enviadas = 0
            for cliente in clientes:
                try:
                    vencimento = cliente["vencimento"]
                    dias_vencimento = (vencimento - hoje).days

                    if dias_vencimento == -1:
                        # 1 dia após o vencimento
                        if self._enviar_mensagem_cliente(
                            cliente, "vencimento_1dia_apos", chat_id_usuario
                        ):
                            enviadas += 1
                            logger.info(
                                f"💰 Cobrança enviada: {cliente['nome']} (vencido há 1 dia) - Usuário {chat_id_usuario}"
                            )
                    elif dias_vencimento == 0:
                        # vence hoje
                        if self._enviar_mensagem_cliente(
                            cliente, "vencimento_hoje", chat_id_usuario
                        ):
                            enviadas += 1
                            logger.info(
                                f"🚨 Alerta enviado: {cliente['nome']} (vence hoje) - Usuário {chat_id_usuario}"
                            )
                    elif dias_vencimento == 1:
                        # 1 dia antes (se existir template próprio, senão usa 2 dias)
                        tipo = "vencimento_1dia"
                        if not self.db.obter_template_por_tipo(
                            tipo, chat_id_usuario
                        ):
                            tipo = "vencimento_2dias"
                        if self._enviar_mensagem_cliente(
                            cliente, tipo, chat_id_usuario
                        ):
                            enviadas += 1
                            logger.info(
                                f"⏰ Lembrete enviado: {cliente['nome']} (vence amanhã) - Usuário {chat_id_usuario}"
                            )
                    elif dias_vencimento == 2:
                        # 2 dias antes
                        if self._enviar_mensagem_cliente(
                            cliente, "vencimento_2dias", chat_id_usuario
                        ):
                            enviadas += 1
                            logger.info(
                                f"⏰ Lembrete enviado: {cliente['nome']} (vence em 2 dias) - Usuário {chat_id_usuario}"
                            )
                    elif dias_vencimento > 2:
                        logger.debug(
                            f"Cliente {cliente['nome']} vence em {dias_vencimento} dias - aguardando"
                        )
                except Exception as e:
                    logger.error(
                        f"Erro ao processar cliente {cliente.get('nome', 'unknown')}: {e}"
                    )

            return enviadas

        except Exception as e:
            logger.error(
                f"Erro ao processar clientes do usuário {chat_id_usuario}: {e}"
            )
            return 0

    # ------------------------------------------------------------------
    # Envio imediato para um cliente (respeita preferências e duplicidade)
    # ------------------------------------------------------------------
    def _enviar_mensagem_cliente(self, cliente, tipo_template, chat_id_usuario=None):
        """Envia mensagem imediatamente para o cliente (com validações)."""
        try:
            # Resolve chat_id do usuário
            resolved_chat_id = chat_id_usuario or cliente.get("chat_id_usuario")
            if not resolved_chat_id:
                logger.error(
                    f"Cliente {cliente.get('nome')} sem chat_id_usuario - não pode enviar WhatsApp"
                )
                return False

            # Verifica preferências de notificação
            if not self._cliente_pode_receber_mensagem(cliente, tipo_template):
                logger.info(
                    f"Cliente {cliente['nome']} optou por não receber mensagens do tipo {tipo_template}"
                )
                return False

            # Busca template isolado por usuário
            template = self.db.obter_template_por_tipo(tipo_template, resolved_chat_id)
            if not template:
                logger.warning(
                    f"Template {tipo_template} não encontrado para usuário {resolved_chat_id}"
                )
                return False

            mensagem = self.template_manager.processar_template(
                template["conteudo"], cliente
            )

            # Evita duplicidade no mesmo dia
            if self._ja_enviada_hoje(cliente["id"], template["id"]):
                logger.info(
                    f"Mensagem {tipo_template} já enviada hoje para {cliente['nome']}"
                )
                return False

            # Envia via Baileys
            resultado = self.baileys_api.send_message(
                cliente["telefone"], mensagem, resolved_chat_id
            )
            sucesso = bool(resultado and resultado.get("success"))

            if sucesso:
                self.db.registrar_envio(
                    cliente_id=cliente["id"],
                    template_id=template["id"],
                    telefone=cliente["telefone"],
                    mensagem=mensagem,
                    tipo_envio="automatico",
                    sucesso=True,
                    chat_id_usuario=resolved_chat_id,
                )
                return True
            else:
                logger.error(f"Falha ao enviar mensagem para {cliente['nome']}")
                return False
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para cliente: {e}")
            return False

    def _cliente_pode_receber_mensagem(self, cliente, tipo_template):
        """Verifica se o cliente pode receber mensagens com base nas preferências."""
        try:
            cliente_id = cliente["id"]
            chat_id_usuario = cliente.get("chat_id_usuario")

            if hasattr(self.db, "cliente_pode_receber_cobranca"):
                # Mensagens de cobrança/vencimento
                if tipo_template in [
                    "vencimento_1dia_apos",
                    "vencimento_hoje",
                    "vencimento_2dias",
                    "vencimento_1dia",
                ]:
                    pode = self.db.cliente_pode_receber_cobranca(
                        cliente_id, chat_id_usuario
                    )
                    logger.info(
                        f"Cliente {cliente['nome']}: pode receber cobrança = {pode}"
                    )
                    return pode
                # Outras notificações
                pode = self.db.cliente_pode_receber_notificacoes(
                    cliente_id, chat_id_usuario
                )
                logger.info(
                    f"Cliente {cliente['nome']}: pode receber notificações = {pode}"
                )
                return pode
            else:
                logger.warning(
                    "Métodos de verificação de preferências não disponíveis - permitindo envio"
                )
                return True
        except Exception as e:
            logger.error(f"Erro ao verificar preferências de notificação: {e}")
            return True  # Mantém funcionalidade em caso de erro

    # ------------------------------------------------------------------
    # Verificação diária às 05:00 (agenda apenas as mensagens de HOJE)
    # ------------------------------------------------------------------
    def _verificar_e_agendar_mensagens_do_dia(self):
        """Verifica clientes às 05h e agenda mensagens que devem ser enviadas HOJE."""
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
                    vencimento = cliente["vencimento"]
                    dias_vencimento = (vencimento - hoje).days

                    # Regras: agenda SOMENTE o que deve sair HOJE
                    if dias_vencimento == -1:
                        self._agendar_mensagem_vencimento(
                            cliente, "vencimento_1dia_apos", hoje
                        )
                        contador_agendadas += 1
                        logger.info(
                            f"📧 Cobrança agendada: {cliente['nome']} (vencido há 1 dia)"
                        )
                    elif dias_vencimento < -1:
                        logger.info(
                            f"⏭️  {cliente['nome']} vencido há {abs(dias_vencimento)} dias - ignorado"
                        )
                    elif dias_vencimento == 0:
                        self._agendar_mensagem_vencimento(
                            cliente, "vencimento_hoje", hoje
                        )
                        contador_agendadas += 1
                        logger.info(
                            f"🚨 Alerta vencimento: {cliente['nome']} (vence hoje)"
                        )
                    elif dias_vencimento == 1:
                        # tenta 1 dia; se não houver template, cai para 2 dias
                        tipo = "vencimento_1dia"
                        if not self.db.obter_template_por_tipo(
                            tipo, cliente.get("chat_id_usuario")
                        ):
                            tipo = "vencimento_2dias"
                        self._agendar_mensagem_vencimento(cliente, tipo, hoje)
                        contador_agendadas += 1
                        logger.info(
                            f"⏰ Lembrete agendado: {cliente['nome']} (vence amanhã)"
                        )
                    elif dias_vencimento == 2:
                        self._agendar_mensagem_vencimento(
                            cliente, "vencimento_2dias", hoje
                        )
                        contador_agendadas += 1
                        logger.info(
                            f"📅 Lembrete agendado: {cliente['nome']} (vence em 2 dias)"
                        )
                    elif dias_vencimento > 2:
                        logger.debug(
                            f"✅ {cliente['nome']} vence em {dias_vencimento} dias - aguardar"
                        )

                except Exception as e:
                    logger.error(f"Erro ao verificar cliente {cliente['nome']}: {e}")

            logger.info(
                f"=== VERIFICAÇÃO CONCLUÍDA: {contador_agendadas} mensagens agendadas para HOJE ==="
            )

        except Exception as e:
            logger.error(f"Erro na verificação diária às 5h: {e}")

    def _agendar_mensagem_vencimento(self, cliente, tipo_template, data_envio):
        """Agenda mensagem específica de vencimento para envio no mesmo dia."""
        try:
            # Buscar template correspondente (isolado por usuário)
            template = self.db.obter_template_por_tipo(
                tipo_template, chat_id_usuario=cliente.get("chat_id_usuario")
            )
            if not template:
                logger.warning(f"Template {tipo_template} não encontrado")
                return

            mensagem = self.template_manager.processar_template(
                template["conteudo"], cliente
            )

            agora = agora_br()
            # Se já passou das 12h, agenda para +2h (limitado até 23:59 do mesmo dia)
            if agora.hour >= 12:
                limite_hoje = agora.replace(hour=23, minute=59, second=0, microsecond=0)
                datetime_envio = min(agora + timedelta(hours=2), limite_hoje)
            else:
                # Agenda para 12:00 do dia corrente
                naive_noon = datetime.combine(data_envio, dtime(12, 0))
                datetime_envio = self.tz.localize(naive_noon)

            # Evita duplicata já agendada para o mesmo dia
            if self.db.verificar_mensagem_existente(
                cliente["id"], template["id"], data_envio
            ):
                logger.info(
                    f"Mensagem {tipo_template} já agendada para {cliente['nome']}"
                )
                return

            # Adiciona à fila
            self.db.adicionar_fila_mensagem(
                cliente_id=cliente["id"],
                template_id=template["id"],
                telefone=cliente["telefone"],
                mensagem=mensagem,
                tipo_mensagem=tipo_template,
                agendado_para=datetime_envio,
            )

            logger.info(
                f"Mensagem {tipo_template} agendada para {cliente['nome']} - ENVIO: {datetime_envio.strftime('%d/%m/%Y %H:%M')}"
            )

        except Exception as e:
            logger.error(f"Erro ao agendar mensagem de vencimento: {e}")

    # ------------------------------------------------------------------
    # Limpeza de fila & cancelamentos
    # ------------------------------------------------------------------
    def _limpar_fila_antiga(self):
        """Remove mensagens antigas processadas e futuras desnecessárias."""
        try:
            logger.info("Iniciando limpeza da fila antiga...")
            removidas_antigas = self.db.limpar_fila_processadas(dias=7)
            removidas_futuras = self.db.limpar_mensagens_futuras()
            logger.info(
                f"Limpeza concluída: {removidas_antigas} antigas e {removidas_futuras} futuras removidas"
            )
        except Exception as e:
            logger.error(f"Erro na limpeza da fila: {e}")

    def cancelar_mensagens_cliente_renovado(self, cliente_id):
        """Cancela todas as mensagens pendentes na fila quando o cliente é renovado."""
        try:
            logger.info(
                f"Cancelando mensagens na fila para cliente renovado ID: {cliente_id}"
            )
            mensagens_pendentes = self.db.buscar_mensagens_fila_cliente(
                cliente_id, apenas_pendentes=True
            )
            if not mensagens_pendentes:
                logger.info(
                    f"Nenhuma mensagem pendente encontrada para cliente ID: {cliente_id}"
                )
                return 0

            canceladas = 0
            for mensagem in mensagens_pendentes:
                try:
                    if self.db.cancelar_mensagem_fila(mensagem["id"]):
                        canceladas += 1
                        logger.info(
                            f"Mensagem ID {mensagem['id']} cancelada (cliente renovado)"
                        )
                except Exception as e:
                    logger.error(
                        f"Erro ao cancelar mensagem ID {mensagem.get('id', 'unknown')}: {e}"
                    )

            logger.info(f"Cliente renovado: {canceladas} mensagens canceladas da fila")
            return canceladas
        except Exception as e:
            logger.error(f"Erro ao cancelar mensagens de cliente renovado: {e}")
            return 0

    # ------------------------------------------------------------------
    # Alertas diários para cada usuário
    # ------------------------------------------------------------------
    def _enviar_alertas_usuarios(self):
        """Envia alerta diário consolidado para cada usuário, sobre seus clientes."""
        try:
            logger.info("Enviando alertas diários isolados por usuário...")
            usuarios_ativos = self._obter_usuarios_ativos()
            if not usuarios_ativos:
                logger.info("Nenhum usuário ativo para envio de alertas")
                return

            for usuario in usuarios_ativos:
                chat_id_usuario = usuario["chat_id"]
                try:
                    self._enviar_alerta_usuario_individual(chat_id_usuario)
                except Exception as e:
                    logger.error(
                        f"Erro ao enviar alerta para usuário {chat_id_usuario}: {e}"
                    )

            logger.info(f"Alertas enviados para {len(usuarios_ativos)} usuários")
        except Exception as e:
            logger.error(f"Erro no envio de alertas diários: {e}")

    def _enviar_alerta_usuario_individual(self, chat_id_usuario):
        """Envia alerta diário para UM usuário específico (somente seus clientes)."""
        try:
            import os
            import requests

            logger.info(f"Enviando alerta diário para usuário {chat_id_usuario}...")

            hoje = agora_br().date()
            clientes_hoje = []
            clientes_proximos = []
            clientes_vencidos = []

            clientes = self.db.listar_clientes(
                apenas_ativos=True, chat_id_usuario=chat_id_usuario
            )
            for cliente in clientes:
                try:
                    vencimento = cliente["vencimento"]
                    dias = (vencimento - hoje).days
                    if dias == 0:
                        clientes_hoje.append(cliente)
                    elif 1 <= dias <= 7:
                        clientes_proximos.append(cliente)
                    elif dias < 0:
                        clientes_vencidos.append(cliente)
                except Exception as e:
                    logger.error(
                        f"Erro ao processar cliente {cliente.get('nome', 'unknown')}: {e}"
                    )

            if clientes_hoje or clientes_proximos or clientes_vencidos:
                mensagem = (
                    f"🚨 *ALERTA DIÁRIO - VENCIMENTOS*\n"
                    f"📅 *{hoje.strftime('%d/%m/%Y')}*\n\n"
                )
                if clientes_vencidos:
                    mensagem += f"🔴 *VENCIDOS ({len(clientes_vencidos)}):*\n"
                    for c in clientes_vencidos[:5]:
                        dias_venc = abs((c["vencimento"] - hoje).days)
                        mensagem += f"• {c['nome']} - há {dias_venc} dias\n"
                    if len(clientes_vencidos) > 5:
                        mensagem += f"• +{len(clientes_vencidos) - 5} outros vencidos\n"
                    mensagem += "\n"
                if clientes_hoje:
                    mensagem += f"⚠️ *VENCEM HOJE ({len(clientes_hoje)}):*\n"
                    for c in clientes_hoje:
                        valor = c.get("valor")
                        if isinstance(valor, (int, float)):
                            mensagem += f"• {c['nome']} - R$ {valor:.2f}\n"
                        else:
                            mensagem += f"• {c['nome']}\n"
                    mensagem += "\n"
                if clientes_proximos:
                    mensagem += f"📅 *PRÓXIMOS 7 DIAS ({len(clientes_proximos)}):*\n"
                    for c in clientes_proximos[:5]:
                        dias_rest = (c["vencimento"] - hoje).days
                        mensagem += f"• {c['nome']} - {dias_rest} dias\n"
                    if len(clientes_proximos) > 5:
                        mensagem += f"• +{len(clientes_proximos) - 5} outros próximos\n"
                    mensagem += "\n"
                mensagem += (
                    f"📊 *RESUMO:*\n"
                    f"• Total clientes ativos: {len(clientes)}\n"
                    f"• Vencidos: {len(clientes_vencidos)}\n"
                    f"• Vencem hoje: {len(clientes_hoje)}\n"
                    f"• Próximos 7 dias: {len(clientes_proximos)}\n\n"
                    f"💡 Use o comando `/vencimentos` para ver detalhes"
                )
            else:
                mensagem = (
                    f"✅ *RELATÓRIO DIÁRIO*\n"
                    f"📅 *{hoje.strftime('%d/%m/%Y')}*\n\n"
                    f"🎉 Nenhum cliente vencendo hoje!\n"
                    f"📊 Total de clientes ativos: {len(clientes)}\n\n"
                    f"Tudo sob controle! 👍"
                )

            # Enviar para o próprio usuário (e não para ADMIN por padrão)
            if self.bot:
                self.bot.send_message(chat_id_usuario, mensagem, parse_mode="Markdown")
            else:
                bot_token = os.getenv("BOT_TOKEN")
                if not bot_token:
                    logger.error("BOT_TOKEN não configurado para envio de alerta")
                    return
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(
                    url,
                    data={
                        "chat_id": chat_id_usuario,
                        "text": mensagem,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )

            logger.info(f"Alerta diário enviado para {chat_id_usuario}")

        except Exception as e:
            logger.error(f"Erro ao enviar alerta para usuário {chat_id_usuario}: {e}")

    # ------------------------------------------------------------------
    # Processamentos auxiliares (forçados, personalizados, consultas)
    # ------------------------------------------------------------------
    def processar_todos_vencidos(self, forcar_reprocesso=False):
        """Processa TODOS os clientes vencidos (útil ao mudar horários)."""
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
                    vencimento = cliente["vencimento"]
                    dias_vencimento = (vencimento - hoje).days

                    if dias_vencimento < 0:  # qualquer vencido
                        if not forcar_reprocesso:
                            template = self.db.obter_template_por_tipo(
                                "vencimento_1dia_apos", cliente.get("chat_id_usuario")
                            )
                            if template and self._ja_enviada_hoje(
                                cliente["id"], template["id"]
                            ):
                                logger.info(
                                    f"⏭️  {cliente['nome']} - mensagem já enviada hoje"
                                )
                                continue
                        if self._enviar_mensagem_cliente(
                            cliente, "vencimento_1dia_apos", cliente.get("chat_id_usuario")
                        ):
                            enviadas += 1
                            logger.info(
                                f"📧 Cobrança enviada: {cliente['nome']} (vencido há {abs(dias_vencimento)} dias)"
                            )
                    elif dias_vencimento == 0:
                        if self._enviar_mensagem_cliente(
                            cliente, "vencimento_hoje", cliente.get("chat_id_usuario")
                        ):
                            enviadas += 1
                            logger.info(
                                f"🚨 Alerta enviado: {cliente['nome']} (vence hoje)"
                            )
                    elif dias_vencimento == 1:
                        tipo = "vencimento_1dia"
                        if not self.db.obter_template_por_tipo(
                            tipo, cliente.get("chat_id_usuario")
                        ):
                            tipo = "vencimento_2dias"
                        if self._enviar_mensagem_cliente(
                            cliente, tipo, cliente.get("chat_id_usuario")
                        ):
                            enviadas += 1
                            logger.info(
                                f"⏰ Lembrete enviado: {cliente['nome']} (vence amanhã)"
                            )
                    elif dias_vencimento == 2:
                        if self._enviar_mensagem_cliente(
                            cliente, "vencimento_2dias", cliente.get("chat_id_usuario")
                        ):
                            enviadas += 1
                            logger.info(
                                f"⏰ Lembrete enviado: {cliente['nome']} (vence em 2 dias)"
                            )

                except Exception as e:
                    logger.error(f"Erro ao processar cliente {cliente['nome']}: {e}")

            logger.info(
                f"=== PROCESSAMENTO FORÇADO CONCLUÍDO: {enviadas} mensagens enviadas ==="
            )
            return enviadas

        except Exception as e:
            logger.error(f"Erro no processamento forçado de vencidos: {e}")
            return 0

    def _verificar_usuarios_sistema(self, data_vencimento):
        """Verifica usuários do sistema que precisam de alerta de pagamento."""
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
                    (data_vencimento,),
                )
                usuarios_vencendo = cursor.fetchall()

            if usuarios_vencendo:
                logger.info(
                    f"Encontrados {len(usuarios_vencendo)} usuários em teste vencendo em {formatar_data_br(data_vencimento)}"
                )
                for usuario in usuarios_vencendo:
                    try:
                        self._enviar_alerta_teste_vencendo(dict(usuario))
                    except Exception as e:
                        logger.error(
                            f"Erro ao enviar alerta para usuário {usuario.get('chat_id')}: {e}"
                        )
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
                    (data_vencimento,),
                )
                usuarios_vencendo = cursor.fetchall()

            if usuarios_vencendo:
                logger.info(
                    f"Encontrados {len(usuarios_vencendo)} usuários pagos vencendo em {formatar_data_br(data_vencimento)}"
                )
                for usuario in usuarios_vencendo:
                    try:
                        self._enviar_alerta_renovacao(dict(usuario))
                    except Exception as e:
                        logger.error(
                            f"Erro ao enviar alerta de renovação para usuário {usuario.get('chat_id')}: {e}"
                        )
        except Exception as e:
            logger.error(f"Erro ao verificar usuários pagos vencendo: {e}")

    def _enviar_alerta_teste_vencendo(self, usuario):
        try:
            chat_id = usuario.get("chat_id")
            nome = usuario.get("nome", "usuário")
            fim_teste = usuario.get("fim_periodo_teste")

            if isinstance(fim_teste, datetime):
                data_vencimento = fim_teste.strftime("%d/%m/%Y")
            else:
                data_vencimento = "amanhã"

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
                    {"text": "💳 Gerar PIX - R$ 20,00", "callback_data": f"gerar_pix_usuario_{chat_id}"}
                ],
                [
                    {"text": "📞 Falar com Suporte", "url": "https://t.me/seu_suporte"},
                    {"text": "❓ Dúvidas", "callback_data": "info_planos"},
                ],
            ]

            if hasattr(self, "bot") and self.bot:
                self.bot.send_message(
                    chat_id,
                    mensagem,
                    parse_mode="Markdown",
                    reply_markup={"inline_keyboard": inline_keyboard},
                )
                logger.info(f"Alerta de teste vencendo enviado para {nome} (ID: {chat_id})")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de teste vencendo: {e}")

    def _enviar_alerta_renovacao(self, usuario):
        try:
            chat_id = usuario.get("chat_id")
            nome = usuario.get("nome", "usuário")
            vencimento = usuario.get("proximo_vencimento")

            if isinstance(vencimento, datetime):
                data_vencimento = vencimento.strftime("%d/%m/%Y")
            else:
                data_vencimento = "amanhã"

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
                    {
                        "text": "🔄 Renovar - Gerar PIX R$ 20,00",
                        "callback_data": f"gerar_pix_renovacao_{chat_id}",
                    }
                ],
                [
                    {"text": "📞 Falar com Suporte", "url": "https://t.me/seu_suporte"},
                    {"text": "📋 Minha Conta", "callback_data": "minha_conta"},
                ],
            ]

            if hasattr(self, "bot") and self.bot:
                self.bot.send_message(
                    chat_id,
                    mensagem,
                    parse_mode="Markdown",
                    reply_markup={"inline_keyboard": inline_keyboard},
                )
                logger.info(f"Alerta de renovação enviado para {nome} (ID: {chat_id})")
        except Exception as e:
            logger.error(f"Erro ao enviar alerta de renovação: {e}")

    # ------------------------------------------------------------------
    # Agendamentos utilitários / APIs públicas
    # ------------------------------------------------------------------
    def agendar_mensagens_cliente(self, cliente_id):
        """Agenda mensagens para um cliente (usado no cadastro)."""
        try:
            cliente = self.db.buscar_cliente_por_id(cliente_id)
            if not cliente:
                return

            # Agendar em thread separada
            threading.Thread(
                target=self._agendar_mensagens_cliente_sync, args=(cliente,), daemon=True
            ).start()
        except Exception as e:
            logger.error(
                f"Erro ao agendar mensagens para cliente {cliente_id}: {e}"
            )

    def _agendar_mensagens_cliente_sync(self, cliente):
        """Agenda apenas mensagem de boas-vindas para novo cliente.
        Mensagens de vencimento serão agendadas pela verificação diária às 5h.
        """
        try:
            template_boas_vindas = self.db.obter_template_por_tipo("boas_vindas")
            if template_boas_vindas:
                mensagem_boas_vindas = self.template_manager.processar_template(
                    template_boas_vindas["conteudo"], cliente
                )
                agendado_para = agora_br() + timedelta(minutes=5)
                self.db.adicionar_fila_mensagem(
                    cliente_id=cliente["id"],
                    template_id=template_boas_vindas["id"],
                    telefone=cliente["telefone"],
                    mensagem=mensagem_boas_vindas,
                    tipo_mensagem="boas_vindas",
                    agendado_para=agendado_para,
                )
                logger.info(
                    f"Mensagem de boas-vindas agendada para novo cliente: {cliente['nome']}"
                )
        except Exception as e:
            logger.error(f"Erro ao agendar mensagens para cliente: {e}")

    def agendar_mensagem_personalizada(self, cliente_id, template_id, data_hora):
        """Agenda uma mensagem personalizada para data/hora específica."""
        try:
            cliente = self.db.buscar_cliente_por_id(cliente_id)
            template = self.db.obter_template(template_id)
            if not cliente or not template:
                return False

            mensagem = self.template_manager.processar_template(
                template["conteudo"], cliente
            )
            fila_id = self.db.adicionar_fila_mensagem(
                cliente_id=cliente_id,
                template_id=template_id,
                telefone=cliente["telefone"],
                mensagem=mensagem,
                tipo_mensagem="personalizada",
                agendado_para=data_hora,
            )
            logger.info(
                f"Mensagem personalizada agendada para {cliente['nome']} - ID: {fila_id}"
            )
            return fila_id
        except Exception as e:
            logger.error(f"Erro ao agendar mensagem personalizada: {e}")
            return False

    def reagendar_todas_mensagens(self):
        """Reagenda todas as mensagens baseado nos vencimentos atuais."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM fila_mensagens WHERE processado = FALSE"
                    )
                    conn.commit()
            logger.info("Reagendamento de todas as mensagens iniciado")
            return True
        except Exception as e:
            logger.error(f"Erro ao reagendar mensagens: {e}")
            return False

    # ------------------------------------------------------------------
    # Consultas de fila / próximas execuções
    # ------------------------------------------------------------------
    def obter_tarefas_pendentes(self):
        try:
            mensagens = self.db.obter_mensagens_pendentes(limit=100)
            tarefas = []
            for msg in mensagens:
                tarefas.append(
                    {
                        "id": msg["id"],
                        "cliente": msg["cliente_nome"],
                        "telefone": msg["telefone"],
                        "tipo": msg["tipo_mensagem"],
                        "agendado_para": msg["agendado_para"],
                        "tentativas": msg["tentativas"],
                    }
                )
            return tarefas
        except Exception as e:
            logger.error(f"Erro ao obter tarefas pendentes: {e}")
            return []

    def obter_proximas_execucoes(self, limit=10):
        try:
            mensagens = self.db.obter_mensagens_pendentes(limit=limit)
            execucoes = []
            for msg in mensagens:
                execucoes.append(
                    {
                        "data": formatar_datetime_br(self._as_aware(msg["agendado_para"]))
                        if msg.get("agendado_para")
                        else "-",
                        "tipo": msg["tipo_mensagem"],
                        "cliente": msg["cliente_nome"],
                        "telefone": msg["telefone"],
                    }
                )
            return execucoes
        except Exception as e:
            logger.error(f"Erro ao obter próximas execuções: {e}")
            return []

    def obter_fila_mensagens(self):
        return self.obter_tarefas_pendentes()

    # ------------------------------------------------------------------
    # Duplicidade & Configs
    # ------------------------------------------------------------------
    def _ja_enviada_hoje(self, cliente_id, template_id):
        """Retorna True se já houve envio bem-sucedido para este cliente/template hoje."""
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
                        (cliente_id, template_id, hoje),
                    )
                    count = cursor.fetchone()[0]
                    return count > 0
        except Exception as e:
            logger.error(f"Erro ao verificar duplicata: {e}")
            return False

    def _get_horario_config_global(self, chave, default="09:00"):
        """Obtém horário GLOBAL do banco ou usa padrão."""
        try:
            config = self.db.obter_configuracao(chave, chat_id_usuario=None)
            if config:
                return config
        except Exception as e:
            logger.warning(f"Erro ao carregar configuração global {chave}: {e}")
        return default

    def _get_horario_config_usuario(self, chave, chat_id_usuario, default="09:00"):
        """Obtém horário configurado por usuário; se ausente, usa o global/padrão."""
        try:
            config = self.db.obter_configuracao(chave, chat_id_usuario=chat_id_usuario)
            if config:
                return config
            config = self.db.obter_configuracao(chave, chat_id_usuario=None)
            if config:
                return config
        except Exception as e:
            logger.warning(
                f"Erro ao carregar configuração {chave} para usuário {chat_id_usuario}: {e}"
            )
        return default

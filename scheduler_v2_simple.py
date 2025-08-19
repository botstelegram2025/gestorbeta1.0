"""
Sistema de Agendamento SUPER SIMPLIFICADO
Versão final simplificada focada apenas no essencial
"""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from utils import agora_br
import pytz
import requests
import os

logger = logging.getLogger(__name__)

class SimpleScheduler:
    def __init__(self, database_manager, baileys_api, template_manager):
        """Inicializa agendador super simplificado"""
        self.db = database_manager
        self.baileys_api = baileys_api
        self.template_manager = template_manager
        self.bot_instance = None
        
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Sao_Paulo'))
        self.running = False
        
    def start(self):
        """Inicia o agendador"""
        try:
            if not self.running:
                # Job de notificações às 9h05
                self.scheduler.add_job(
                    func=self._notificar_usuarios_diario,
                    trigger=CronTrigger(hour=9, minute=5),
                    id='notificar_usuarios',
                    name='Notificações Diárias 9h05',
                    replace_existing=True
                )
                
                self.scheduler.start()
                self.running = True
                logger.info("✅ Agendador simplificado iniciado: Notificações 9h05")
                
        except Exception as e:
            logger.error(f"Erro ao iniciar agendador: {e}")
    
    def stop(self):
        """Para o agendador"""
        try:
            if self.running:
                self.scheduler.shutdown()
                self.running = False
                logger.info("Agendador parado")
        except Exception as e:
            logger.error(f"Erro ao parar agendador: {e}")
    
    def _notificar_usuarios_diario(self):
        """Notifica cada usuário sobre seus clientes vencendo"""
        try:
            logger.info("=== NOTIFICAÇÕES DIÁRIAS INICIADAS ===")
            hoje = agora_br().date()
            
            # Buscar todos os usuários do sistema
            usuarios = self._buscar_usuarios_sistema()
            logger.info(f"Encontrados {len(usuarios)} usuários para notificar")
            
            for usuario in usuarios:
                try:
                    chat_id = usuario['chat_id']
                    self._enviar_notificacao_usuario(chat_id, hoje)
                except Exception as e:
                    logger.error(f"Erro ao notificar usuário {usuario.get('chat_id', 'desconhecido')}: {e}")
            
            logger.info("=== NOTIFICAÇÕES CONCLUÍDAS ===")
            
        except Exception as e:
            logger.error(f"Erro nas notificações diárias: {e}")
    
    def _buscar_usuarios_sistema(self):
        """Busca usuários ativos do sistema"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT chat_id 
                        FROM usuarios 
                        WHERE status IN ('ativo', 'teste')
                    """)
                    resultados = cursor.fetchall()
                    return [{'chat_id': row[0]} for row in resultados]
        except Exception as e:
            logger.error(f"Erro ao buscar usuários: {e}")
            return []
    
    def _enviar_notificacao_usuario(self, chat_id_usuario, hoje):
        """Envia notificação individual para um usuário"""
        try:
            logger.info(f"Enviando notificação para usuário {chat_id_usuario}")
            
            # Buscar clientes APENAS deste usuário
            clientes = self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=chat_id_usuario)
            
            if not clientes:
                logger.info(f"Usuário {chat_id_usuario} não tem clientes ativos")
                return
            
            # Categorizar clientes
            vencidos = []
            vence_hoje = []
            vence_proximos = []
            
            for cliente in clientes:
                vencimento = cliente['vencimento']
                dias_diferenca = (vencimento - hoje).days
                
                if dias_diferenca < 0:
                    vencidos.append(cliente)
                elif dias_diferenca == 0:
                    vence_hoje.append(cliente)
                elif 1 <= dias_diferenca <= 7:
                    vence_proximos.append(cliente)
            
            # Criar mensagem apenas se houver algo importante
            if vencidos or vence_hoje or vence_proximos:
                mensagem = f"🚨 *ALERTA DIÁRIO - {hoje.strftime('%d/%m/%Y')}*\n\n"
                
                if vencidos:
                    mensagem += f"🔴 *VENCIDOS ({len(vencidos)}):*\n"
                    for cliente in vencidos[:3]:
                        dias_vencido = abs((cliente['vencimento'] - hoje).days)
                        mensagem += f"• {cliente['nome']} - há {dias_vencido} dia(s)\n"
                    if len(vencidos) > 3:
                        mensagem += f"• +{len(vencidos) - 3} outros\n"
                    mensagem += "\n"
                
                if vence_hoje:
                    mensagem += f"⚠️ *VENCEM HOJE ({len(vence_hoje)}):*\n"
                    for cliente in vence_hoje:
                        mensagem += f"• {cliente['nome']} - R$ {cliente['valor']:.2f}\n"
                    mensagem += "\n"
                
                if vence_proximos:
                    mensagem += f"📅 *PRÓXIMOS 7 DIAS ({len(vence_proximos)}):*\n"
                    for cliente in vence_proximos[:3]:
                        dias_restantes = (cliente['vencimento'] - hoje).days
                        mensagem += f"• {cliente['nome']} - {dias_restantes} dia(s)\n"
                    if len(vence_proximos) > 3:
                        mensagem += f"• +{len(vence_proximos) - 3} outros\n"
                
                mensagem += f"\n📊 Total de clientes: {len(clientes)}\n"
                mensagem += "💡 Use /vencimentos para detalhes"
                
                # Enviar para o usuário
                sucesso = self._enviar_telegram(chat_id_usuario, mensagem)
                if sucesso:
                    logger.info(f"📱 Notificação enviada com sucesso para usuário {chat_id_usuario}")
                else:
                    logger.error(f"Falha ao enviar notificação para usuário {chat_id_usuario}")
            else:
                logger.info(f"Usuário {chat_id_usuario} não tem vencimentos próximos")
            
        except Exception as e:
            logger.error(f"Erro ao notificar usuário {chat_id_usuario}: {e}")
    
    def _enviar_telegram(self, chat_id, mensagem):
        """Envia mensagem via Telegram"""
        try:
            bot_token = os.getenv('BOT_TOKEN')
            if not bot_token:
                logger.error("BOT_TOKEN não configurado")
                return False
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': mensagem,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Erro Telegram: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar Telegram: {e}")
            return False
    
    def is_running(self):
        """Verifica se agendador está rodando"""
        return self.running and self.scheduler.running if self.scheduler else False
    
    def set_bot_instance(self, bot_instance):
        """Define instância do bot (compatibilidade)"""
        self.bot_instance = bot_instance
        logger.info("Bot instance configurada no agendador simplificado")
    
    def reagendar_manual(self):
        """Execução manual para teste"""
        try:
            logger.info("🔄 EXECUÇÃO MANUAL DE TESTE")
            self._notificar_usuarios_diario()
            logger.info("✅ EXECUÇÃO MANUAL CONCLUÍDA")
        except Exception as e:
            logger.error(f"Erro na execução manual: {e}")
    
    def processar_todos_vencidos(self, forcar_reprocesso=False):
        """Compatibilidade: processa todos os vencidos"""
        try:
            logger.info("🔄 Processamento de todos os vencidos solicitado")
            # No sistema simplificado, apenas notificamos os usuários
            self._notificar_usuarios_diario()
            logger.info("✅ Processamento concluído")
            return 0
        except Exception as e:
            logger.error(f"Erro no processamento: {e}")
            return 0
    
    def _setup_main_jobs(self):
        """Compatibilidade: recria jobs principais"""
        try:
            logger.info("🔄 Recriando jobs do agendador...")
            
            # Remove jobs existentes
            for job in list(self.scheduler.get_jobs()):
                job.remove()
            
            # Recria job de notificações
            self.scheduler.add_job(
                func=self._notificar_usuarios_diario,
                trigger=CronTrigger(hour=9, minute=5),
                id='notificar_usuarios',
                name='Notificações Diárias 9h05',
                replace_existing=True
            )
            
            logger.info("✅ Jobs recriados com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao recriar jobs: {e}")
            return False
    
    def get_jobs(self):
        """Compatibilidade: retorna lista de jobs"""
        try:
            return self.scheduler.get_jobs() if self.scheduler else []
        except Exception as e:
            logger.error(f"Erro ao obter jobs: {e}")
            return []
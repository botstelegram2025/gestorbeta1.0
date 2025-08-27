"""
Configurações do Sistema
Gerencia configurações centralizadas e validações de ambiente
"""

import os
import sys
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Configurações do banco de dados PostgreSQL"""
    host: str
    port: int
    database: str
    username: str
    password: str
    
    @property
    def connection_url(self) -> str:
        """URL de conexão PostgreSQL"""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def validate(self) -> bool:
        """Valida configurações do banco"""
        required_fields = [self.host, self.database, self.username, self.password]
        return all(field for field in required_fields)

@dataclass
class BotConfig:
    """Configurações do Bot Telegram"""
    token: str
    admin_chat_id: int
    admin_phone: str
    webhook_url: Optional[str] = None
    webhook_port: int = 8443
    
    def validate(self) -> bool:
        """Valida configurações do bot"""
        return bool(self.token and self.admin_chat_id)

@dataclass
class BaileysConfig:
    """Configurações da API Baileys"""
    api_url: str
    api_key: str
    session_name: str
    timeout: int = 30
    max_retries: int = 3
    message_delay: int = 2
    auto_reconnect: bool = True
    
    def validate(self) -> bool:
        """Valida configurações do Baileys"""
        return bool(self.api_url and self.session_name)

@dataclass
class SystemConfig:
    """Configurações gerais do sistema"""
    log_level: str = "INFO"
    timezone: str = "America/Sao_Paulo"
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    maintenance_mode: bool = False
    debug_mode: bool = False
    
    def validate(self) -> bool:
        """Valida configurações do sistema"""
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        return self.log_level.upper() in valid_log_levels

class Config:
    """Classe principal de configurações"""
    
    def __init__(self):
        """Inicializa configurações carregando variáveis de ambiente"""
        self._load_environment()
        
        # Configurações do banco de dados
        self.database = DatabaseConfig(
            host=os.getenv('PGHOST', 'localhost'),
            port=int(os.getenv('PGPORT', '5432')),
            database=os.getenv('PGDATABASE', 'bot_clientes'),
            username=os.getenv('PGUSER', 'postgres'),
            password=os.getenv('PGPASSWORD', '')
        )
        
        # Configurações do bot
        self.bot = BotConfig(
            token=os.getenv('BOT_TOKEN', ''),
            admin_chat_id=int(os.getenv('ADMIN_CHAT_ID', '0')),
            admin_phone=os.getenv('ADMIN_PHONE', ''),
            webhook_url=os.getenv('WEBHOOK_URL'),
            webhook_port=int(os.getenv('WEBHOOK_PORT', '8443'))
        )
        
        # Configurações do Baileys
        self.baileys = BaileysConfig(
            api_url=os.getenv('BAILEYS_API_URL', 'http://baileys-local-persist.railway.internal:3000'),
            api_key=os.getenv('BAILEYS_API_KEY', ''),
            session_name=os.getenv('BAILEYS_SESSION', 'bot_clientes'),
            timeout=int(os.getenv('BAILEYS_TIMEOUT', '30')),
            max_retries=int(os.getenv('BAILEYS_MAX_RETRIES', '3')),
            message_delay=int(os.getenv('BAILEYS_MESSAGE_DELAY', '2')),
            auto_reconnect=os.getenv('BAILEYS_AUTO_RECONNECT', 'true').lower() == 'true'
        )
        
        # Configurações do sistema
        self.system = SystemConfig(
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            timezone=os.getenv('TIMEZONE', 'America/Sao_Paulo'),
            backup_enabled=os.getenv('BACKUP_ENABLED', 'true').lower() == 'true',
            backup_interval_hours=int(os.getenv('BACKUP_INTERVAL_HOURS', '24')),
            maintenance_mode=os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true',
            debug_mode=os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        )
        
        # Configurações de empresa
        self.empresa = {
            'nome': os.getenv('EMPRESA_NOME', ''),
            'telefone': os.getenv('EMPRESA_TELEFONE', ''),
            'email': os.getenv('EMPRESA_EMAIL', ''),
            'site': os.getenv('EMPRESA_SITE', ''),
            'endereco': os.getenv('EMPRESA_ENDERECO', '')
        }
        
        # Configurações de PIX
        self.pix = {
            'chave': os.getenv('PIX_CHAVE', ''),
            'beneficiario': os.getenv('PIX_BENEFICIARIO', ''),
            'banco': os.getenv('PIX_BANCO', ''),
            'agencia': os.getenv('PIX_AGENCIA', ''),
            'conta': os.getenv('PIX_CONTA', '')
        }
        
        # Configurações de suporte
        self.suporte = {
            'telefone': os.getenv('SUPORTE_TELEFONE', ''),
            'email': os.getenv('SUPORTE_EMAIL', ''),
            'horario': os.getenv('SUPORTE_HORARIO', 'Segunda a Sexta, 9h às 18h'),
            'whatsapp': os.getenv('SUPORTE_WHATSAPP', '')
        }
    
    def _load_environment(self):
        """Carrega variáveis do arquivo .env se existir"""
        try:
            from dotenv import load_dotenv
            
            # Procurar arquivo .env
            env_path = Path('.env')
            if env_path.exists():
                load_dotenv(env_path)
                logger.info("Arquivo .env carregado com sucesso")
            else:
                logger.info("Arquivo .env não encontrado, usando variáveis do sistema")
                
        except ImportError:
            logger.warning("python-dotenv não instalado, usando apenas variáveis do sistema")
    
    def validate_all(self) -> Dict[str, Any]:
        """Valida todas as configurações"""
        validation_results = {
            'database': self.database.validate(),
            'bot': self.bot.validate(),
            'baileys': self.baileys.validate(),
            'system': self.system.validate(),
            'errors': [],
            'warnings': []
        }
        
        # Verificar configurações críticas
        if not validation_results['database']:
            validation_results['errors'].append("Configurações do banco de dados incompletas")
        
        if not validation_results['bot']:
            validation_results['errors'].append("Token do bot ou ID do admin não configurados")
        
        if not validation_results['baileys']:
            validation_results['warnings'].append("Configurações do Baileys incompletas")
        
        # Verificar configurações opcionais
        if not self.empresa['nome']:
            validation_results['warnings'].append("Nome da empresa não configurado")
        
        if not self.pix['chave']:
            validation_results['warnings'].append("Chave PIX não configurada")
        
        if not self.suporte['telefone']:
            validation_results['warnings'].append("Telefone de suporte não configurado")
        
        validation_results['valid'] = len(validation_results['errors']) == 0
        
        return validation_results
    
    def get_database_url(self) -> str:
        """Obtém URL de conexão do banco"""
        return self.database.connection_url
    
    def is_production(self) -> bool:
        """Verifica se está em ambiente de produção"""
        return os.getenv('ENVIRONMENT', 'development').lower() == 'production'
    
    def is_debug_enabled(self) -> bool:
        """Verifica se debug está habilitado"""
        return self.system.debug_mode or os.getenv('DEBUG', 'false').lower() == 'true'
    
    def get_log_level(self) -> int:
        """Obtém nível de log numérico"""
        levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        return levels.get(self.system.log_level.upper(), logging.INFO)
    
    def configure_logging(self):
        """Configura sistema de logging"""
        # Formato das mensagens
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # Configuração básica
        logging.basicConfig(
            level=self.get_log_level(),
            format=log_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Logger específico para o bot
        bot_logger = logging.getLogger('bot')
        bot_logger.setLevel(self.get_log_level())
        
        # Logger para requests (reduzir verbosidade)
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        
        # Se em debug, adicionar mais detalhes
        if self.is_debug_enabled():
            logging.getLogger().setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
            )
            
            # Reconfigurar handlers existentes
            for handler in logging.root.handlers:
                handler.setFormatter(formatter)
        
        logger.info(f"Logging configurado - Nível: {self.system.log_level}")
    
    def print_summary(self):
        """Imprime resumo das configurações"""
        print("\n" + "="*60)
        print("🤖 BOT TELEGRAM - GESTÃO DE CLIENTES")
        print("="*60)
        
        print(f"📊 Ambiente: {'🔴 PRODUÇÃO' if self.is_production() else '🟡 DESENVOLVIMENTO'}")
        print(f"🐛 Debug: {'✅ Ativo' if self.is_debug_enabled() else '❌ Inativo'}")
        print(f"📝 Log Level: {self.system.log_level}")
        print(f"🕐 Timezone: {self.system.timezone}")
        
        print(f"\n📱 Bot Telegram:")
        print(f"   Token: {'✅ Configurado' if self.bot.token else '❌ Não configurado'}")
        print(f"   Admin ID: {self.bot.admin_chat_id if self.bot.admin_chat_id else '❌ Não configurado'}")
        print(f"   Admin Phone: {'✅ Configurado' if self.bot.admin_phone else '❌ Não configurado'}")
        
        print(f"\n🗄️ Banco de Dados:")
        print(f"   Host: {self.database.host}:{self.database.port}")
        print(f"   Database: {self.database.database}")
        print(f"   User: {self.database.username}")
        print(f"   Password: {'✅ Configurado' if self.database.password else '❌ Não configurado'}")
        
        print(f"\n📱 WhatsApp/Baileys:")
        print(f"   API URL: {self.baileys.api_url}")
        print(f"   Session: {self.baileys.session_name}")
        print(f"   API Key: {'✅ Configurado' if self.baileys.api_key else '❌ Não configurado'}")
        print(f"   Auto-reconnect: {'✅ Ativo' if self.baileys.auto_reconnect else '❌ Inativo'}")
        
        print(f"\n🏢 Empresa:")
        print(f"   Nome: {self.empresa['nome'] or '❌ Não configurado'}")
        print(f"   Telefone: {self.empresa['telefone'] or '❌ Não configurado'}")
        print(f"   Email: {self.empresa['email'] or '❌ Não configurado'}")
        
        print(f"\n💳 PIX:")
        print(f"   Chave: {self.pix['chave'] or '❌ Não configurado'}")
        print(f"   Beneficiário: {self.pix['beneficiario'] or '❌ Não configurado'}")
        
        print(f"\n📞 Suporte:")
        print(f"   Telefone: {self.suporte['telefone'] or '❌ Não configurado'}")
        print(f"   Email: {self.suporte['email'] or '❌ Não configurado'}")
        print(f"   Horário: {self.suporte['horario']}")
        
        print("="*60)
        
        # Validação
        validation = self.validate_all()
        if validation['valid']:
            print("✅ Todas as configurações críticas estão válidas!")
        else:
            print("❌ Encontrados problemas nas configurações:")
            for error in validation['errors']:
                print(f"   🔴 {error}")
        
        if validation['warnings']:
            print("⚠️ Avisos de configuração:")
            for warning in validation['warnings']:
                print(f"   🟡 {warning}")
        
        print("="*60 + "\n")
    
    def get_required_env_vars(self) -> Dict[str, str]:
        """Retorna lista de variáveis de ambiente obrigatórias"""
        return {
            'BOT_TOKEN': 'Token do bot Telegram',
            'ADMIN_CHAT_ID': 'ID do chat do administrador',
            'PGHOST': 'Host do PostgreSQL',
            'PGDATABASE': 'Nome do banco PostgreSQL', 
            'PGUSER': 'Usuário do PostgreSQL',
            'PGPASSWORD': 'Senha do PostgreSQL'
        }
    
    def get_optional_env_vars(self) -> Dict[str, str]:
        """Retorna lista de variáveis de ambiente opcionais"""
        return {
            'ADMIN_PHONE': 'Telefone do administrador para testes',
            'BAILEYS_API_URL': 'URL da API Baileys',
            'BAILEYS_API_KEY': 'Chave da API Baileys',
            'BAILEYS_SESSION': 'Nome da sessão Baileys',
            'EMPRESA_NOME': 'Nome da empresa',
            'EMPRESA_TELEFONE': 'Telefone da empresa',
            'EMPRESA_EMAIL': 'Email da empresa',
            'PIX_CHAVE': 'Chave PIX para recebimentos',
            'PIX_BENEFICIARIO': 'Nome do beneficiário PIX',
            'SUPORTE_TELEFONE': 'Telefone de suporte',
            'SUPORTE_EMAIL': 'Email de suporte',
            'LOG_LEVEL': 'Nível de log (DEBUG, INFO, WARNING, ERROR)',
            'TIMEZONE': 'Timezone do sistema',
            'DEBUG_MODE': 'Modo debug (true/false)',
            'MAINTENANCE_MODE': 'Modo manutenção (true/false)'
        }
    
    def export_env_template(self) -> str:
        """Exporta template de arquivo .env"""
        template = "# Configurações do Bot Telegram - Gestão de Clientes\n\n"
        
        template += "# === CONFIGURAÇÕES OBRIGATÓRIAS ===\n"
        for var, desc in self.get_required_env_vars().items():
            current_value = os.getenv(var, '')
            template += f"# {desc}\n"
            if var in ['BOT_TOKEN', 'PGPASSWORD'] and current_value:
                template += f"{var}={current_value[:10]}...\n\n"
            else:
                template += f"{var}={current_value}\n\n"
        
        template += "# === CONFIGURAÇÕES OPCIONAIS ===\n"
        for var, desc in self.get_optional_env_vars().items():
            current_value = os.getenv(var, '')
            template += f"# {desc}\n"
            template += f"{var}={current_value}\n\n"
        
        return template

# Instância global de configurações
config = Config()

# Funções de conveniência
def get_config() -> Config:
    """Retorna instância global de configurações"""
    return config

def validate_environment() -> bool:
    """Valida ambiente rapidamente"""
    validation = config.validate_all()
    return validation['valid']

def setup_logging():
    """Configura logging do sistema"""
    config.configure_logging()

def print_config_summary():
    """Imprime resumo das configurações"""
    config.print_summary()

# Verificar se está sendo executado diretamente
if __name__ == "__main__":
    print_config_summary()
    
    # Gerar template .env se solicitado
    if len(sys.argv) > 1 and sys.argv[1] == '--generate-env':
        template = config.export_env_template()
        
        with open('.env.example', 'w', encoding='utf-8') as f:
            f.write(template)
        
        print("📄 Arquivo .env.example gerado com sucesso!")
        print("   Copie para .env e configure suas variáveis.")

"""
Integração Baileys API (alta performance, múltiplas sessões)
Padrão de endpoints: /sessions/{session}/<acao>
"""

import os
import requests
import logging
from datetime import datetime
import json
import time
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Fallback simples se você não importar de utils
def formatar_datetime_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


class BaileysAPI:
    def __init__(self):
        """Inicializa a integração com Baileys API (performática e sessionizada)"""
        self.base_url = os.getenv('BAILEYS_API_URL', 'http://localhost:3000')
        self.api_key = os.getenv('BAILEYS_API_KEY', '')
        # sessão padrão só como fallback quando não houver chat_id/session explícita
        self.default_session = os.getenv('BAILEYS_SESSION', 'bot_clientes')
        self.timeout = int(os.getenv('BAILEYS_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('BAILEYS_MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('BAILEYS_RETRY_DELAY', '5'))

        # Envio
        self.message_delay = int(os.getenv('BAILEYS_MESSAGE_DELAY', '2'))
        self.auto_reconnect = os.getenv('BAILEYS_AUTO_RECONNECT', 'true').lower() == 'true'

        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Bot-Clientes/1.0'
        }
        if self.api_key:
            self.headers['Authorization'] = f'Bearer {self.api_key}'

        # Cache por sessão
        self._status_cache: Dict[str, Any] = {}
        self._cache_timeout = 300  # 5 min

        logger.info(f"Baileys API inicializada: {self.base_url}")

        # >>> Se seu servidor usa outro layout, ajuste AQUI para máximo desempenho (apenas troca de strings).
        self._paths = {
            "status":          "sessions/{session}/status",
            "qr":              "sessions/{session}/qr",
            "send_message":    "sessions/{session}/send-message",
            "send_image":      "sessions/{session}/send-image",
            "send_document":   "sessions/{session}/send-document",
            "check_number":    "sessions/{session}/check-number",
            "messages":        "sessions/{session}/messages/{number}",
            "chat_info":       "sessions/{session}/chat-info/{number}",
            "restart":         "sessions/{session}/restart",
            "logout":          "sessions/{session}/logout",
            # globais opcionais
            "health":          "health",
            "sessions":        "sessions",
            "status_global":   "status",
        }

    # ---------------------------
    # Sessão / Helpers
    # ---------------------------
    def get_user_session(self, chat_id_usuario: Optional[int]) -> str:
        """Nome de sessão por usuário (performático e determinístico)."""
        if chat_id_usuario is None:
            return self.default_session
        return f"user_{chat_id_usuario}"

    def _resolve_session(self, chat_id_usuario: Optional[int] = None, explicit_session: Optional[str] = None) -> str:
        """Resolve a sessão usada na chamada, sem tentativa extra."""
        if explicit_session:
            return explicit_session
        return self.get_user_session(chat_id_usuario)

    # ---------------------------
    # HTTP Client com retry
    # ---------------------------
    def _make_request(
        self,
        endpoint: str,
        method: str = 'GET',
        data: Optional[Dict] = None,
        retries: Optional[int] = None,
        params: Optional[Dict] = None
    ) -> Dict:
        """Requisição HTTP performática; sem fallback de rotas."""
        if retries is None:
            retries = self.max_retries

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        for attempt in range(retries + 1):
            try:
                if method == 'GET':
                    response = requests.get(url, headers=self.headers, timeout=self.timeout, params=params or data)
                elif method == 'POST':
                    response = requests.post(url, headers=self.headers, timeout=self.timeout, json=data, params=params)
                elif method == 'PUT':
                    response = requests.put(url, headers=self.headers, timeout=self.timeout, json=data, params=params)
                elif method == 'DELETE':
                    response = requests.delete(url, headers=self.headers, timeout=self.timeout, params=params)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")

                logger.debug(f"Baileys API Request: {method} {url} - Status: {response.status_code}")

                if 200 <= response.status_code < 300:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        return {'success': True, 'data': response.text or ''}
                elif response.status_code == 401:
                    return {'success': False, 'error': 'Não autorizado - verifique API Key'}
                elif response.status_code == 404:
                    # **performático**: sem tentativas de outras rotas. Falha rápida e clara.
                    return {'success': False, 'error': 'Endpoint não encontrado'}
                elif response.status_code == 429:
                    return {'success': False, 'error': 'Muitas requisições - tente mais tarde'}
                else:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', f"Erro HTTP {response.status_code}")
                    except Exception:
                        error_msg = response.text or f"Erro HTTP {response.status_code}"

                    if attempt < retries:
                        logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Retentando em {self.retry_delay}s...")
                        time.sleep(self.retry_delay)
                        continue
                    return {'success': False, 'error': error_msg}

            except requests.exceptions.ConnectionError:
                error_msg = "Erro de conexão com Baileys API"
                if attempt < retries:
                    logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Retentando em {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': error_msg}

            except requests.exceptions.Timeout:
                error_msg = "Timeout na requisição para Baileys API"
                if attempt < retries:
                    logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Retentando em {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': error_msg}

            except Exception as e:
                error_msg = f"Erro inesperado: {str(e)}"
                if attempt < retries:
                    logger.warning(f"Tentativa {attempt + 1} falhou: {error_msg}. Retentando em {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': error_msg}

        return {'success': False, 'error': 'Máximo de tentativas excedido'}

    # ---------------------------
    # Status / Sessão
    # ---------------------------
    def get_status(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """Obtém status da sessão específica (cache por sessão)."""
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            now = time.time()
            cache_key = f'status_{session_name}'
            if cache_key in self._status_cache and now - self._status_cache.get(f'{cache_key}_timestamp', 0) < self._cache_timeout:
                return self._status_cache[cache_key]

            endpoint = self._paths["status"].format(session=session_name)
            response = self._make_request(endpoint, 'GET')

            if response.get('success'):
                status_data = response.get('data', {})
                status = {
                    'status': self._format_connection_status(status_data.get('state', 'disconnected')),
                    'numero': (status_data.get('user', {}) or {}).get('id', '').replace('@s.whatsapp.net', ''),
                    'bateria': (status_data.get('battery', {}) or {}).get('percentage'),
                    'ultima_conexao': self._format_last_seen(status_data.get('lastSeen')),
                    'qr_needed': bool(status_data.get('qr')),
                    'mensagens_enviadas': (status_data.get('stats', {}) or {}).get('sent', 0),
                    'mensagens_falharam': (status_data.get('stats', {}) or {}).get('failed', 0),
                    'fila_pendente': (status_data.get('stats', {}) or {}).get('pending', 0),
                    'session': session_name
                }
                self._status_cache[cache_key] = status
                self._status_cache[f'{cache_key}_timestamp'] = now
                return status

            return {
                'status': '🔴 Erro na conexão',
                'numero': 'N/A',
                'bateria': None,
                'ultima_conexao': 'N/A',
                'qr_needed': True,
                'mensagens_enviadas': 0,
                'mensagens_falharam': 0,
                'fila_pendente': 0,
                'error': response.get('error', 'Erro desconhecido'),
                'session': session_name
            }

        except Exception as e:
            logger.error(f"Erro ao obter status: {e}")
            return {
                'status': '❌ Erro interno',
                'numero': 'N/A',
                'bateria': None,
                'ultima_conexao': 'N/A',
                'qr_needed': True,
                'mensagens_enviadas': 0,
                'mensagens_falharam': 0,
                'fila_pendente': 0,
                'error': str(e)
            }

    def _format_connection_status(self, state: str) -> str:
        status_map = {
            'open': '🟢 Conectado',
            'connecting': '🟡 Conectando',
            'close': '🔴 Desconectado',
            'disconnected': '🔴 Desconectado'
        }
        return status_map.get(state, f'❓ {state}')

    def _format_last_seen(self, timestamp) -> str:
        if not timestamp:
            return 'Nunca'
        try:
            if isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp)
            else:
                dt = datetime.fromisoformat(str(timestamp))
            return formatar_datetime_br(dt)
        except Exception:
            return 'Inválido'

    def qr_code_needed(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> bool:
        status = self.get_status(chat_id_usuario, session)
        return status.get('qr_needed', True)

    def generate_qr_code(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """Gera QR Code para a sessão específica (rota única e direta)."""
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["qr"].format(session=session_name)
            response = self._make_request(endpoint, 'GET')

            if response.get('success'):
                data = response.get('data', response)
                return {
                    'success': True,
                    'qr_code': data.get('qr'),
                    'qr_image': data.get('qr_image'),
                    'session': session_name,
                    'instructions': data.get('instructions', '')
                }
            return {'success': False, 'error': response.get('error', 'QR Code não disponível'), 'session': session_name}
        except Exception as e:
            logger.error(f"Erro ao gerar QR Code: {e}")
            return {'success': False, 'error': str(e)}

    # ---------------------------
    # Envio de mensagens
    # ---------------------------
    def send_message(
        self,
        phone: str,
        message: str,
        chat_id_usuario: Optional[int] = None,
        session: Optional[str] = None,
        options: Optional[Dict] = None
    ) -> Dict:
        """Envia mensagem na sessão específica (performático)."""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["send_message"].format(session=session_name)

            payload = {'number': clean_phone, 'message': message}
            if options:
                payload.update(options)

            response = self._make_request(endpoint, 'POST', payload)
            if response.get('success'):
                if self.message_delay > 0:
                    time.sleep(self.message_delay)
                return {
                    'success': True,
                    'messageId': response.get('messageId') or (response.get('data') or {}).get('messageId'),
                    'status': 'sent',
                    'timestamp': response.get('timestamp', time.time()),
                    'session': session_name
                }
            return {'success': False, 'error': response.get('error', 'Erro desconhecido'), 'session': session_name}

        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return {'success': False, 'error': str(e)}

    def send_image(
        self,
        phone: str,
        image_path: str,
        chat_id_usuario: Optional[int] = None,
        session: Optional[str] = None,
        caption: Optional[str] = None
    ) -> Dict:
        """Envia imagem na sessão específica."""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["send_image"].format(session=session_name)

            data = {'number': clean_phone, 'image': image_path}
            if caption:
                data['caption'] = caption

            response = self._make_request(endpoint, 'POST', data)
            if response.get('success') and self.message_delay > 0:
                time.sleep(self.message_delay)
            return response

        except Exception as e:
            logger.error(f"Erro ao enviar imagem: {e}")
            return {'success': False, 'error': str(e)}

    def send_document(
        self,
        phone: str,
        document_path: str,
        filename: Optional[str] = None,
        chat_id_usuario: Optional[int] = None,
        session: Optional[str] = None
    ) -> Dict:
        """Envia documento na sessão específica."""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["send_document"].format(session=session_name)

            data = {'number': clean_phone, 'document': document_path}
            if filename:
                data['filename'] = filename

            response = self._make_request(endpoint, 'POST', data)
            if response.get('success') and self.message_delay > 0:
                time.sleep(self.message_delay)
            return response

        except Exception as e:
            logger.error(f"Erro ao enviar documento: {e}")
            return {'success': False, 'error': str(e)}

    # ---------------------------
    # Informações / Utilidades
    # ---------------------------
    def get_chat_info(self, phone: str, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """Info do chat na sessão específica."""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["chat_info"].format(session=session_name, number=clean_phone)

            return self._make_request(endpoint, 'GET')

        except Exception as e:
            logger.error(f"Erro ao obter info do chat: {e}")
            return {'success': False, 'error': str(e)}

    def is_number_registered(self, phone: str, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """Verifica registro do número na sessão específica."""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["check_number"].format(session=session_name)

            data = {'number': clean_phone}
            return self._make_request(endpoint, 'POST', data)

        except Exception as e:
            logger.error(f"Erro ao verificar número: {e}")
            return {'success': False, 'error': str(e)}

    def reconnect(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """Reinicia a sessão especificada."""
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["restart"].format(session=session_name)

            response = self._make_request(endpoint, 'POST')
            # Limpa cache da sessão
            self._status_cache.pop(f'status_{session_name}', None)
            self._status_cache.pop(f'status_{session_name}_timestamp', None)
            return response

        except Exception as e:
            logger.error(f"Erro ao reconectar: {e}")
            return {'success': False, 'error': str(e)}

    def logout(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """Efetua logout da sessão especificada."""
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["logout"].format(session=session_name)

            response = self._make_request(endpoint, 'POST')
            # Limpa cache da sessão
            self._status_cache.pop(f'status_{session_name}', None)
            self._status_cache.pop(f'status_{session_name}_timestamp', None)
            return response

        except Exception as e:
            logger.error(f"Erro ao fazer logout: {e}")
            return {'success': False, 'error': str(e)}

    def get_config(self) -> Dict:
        """Config atual do cliente."""
        return {
            'base_url': self.base_url,
            'default_session': self.default_session,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'message_delay': self.message_delay,
            'auto_reconnect': self.auto_reconnect,
            'api_key_configured': bool(self.api_key)
        }

    def update_config(self, **kwargs) -> bool:
        """Atualiza config leve (sem I/O extra)."""
        try:
            if 'timeout' in kwargs:
                self.timeout = int(kwargs['timeout'])
            if 'max_retries' in kwargs:
                self.max_retries = int(kwargs['max_retries'])
            if 'message_delay' in kwargs:
                self.message_delay = int(kwargs['message_delay'])
            if 'auto_reconnect' in kwargs:
                self.auto_reconnect = bool(kwargs['auto_reconnect'])
            if 'default_session' in kwargs:
                self.default_session = str(kwargs['default_session'])
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar configurações: {e}")
            return False

    def get_message_history(
        self,
        phone: str,
        limit: int = 50,
        chat_id_usuario: Optional[int] = None,
        session: Optional[str] = None
    ) -> Dict:
        """Histórico de mensagens na sessão específica."""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["messages"].format(session=session_name, number=clean_phone)

            params = {'limit': limit}
            return self._make_request(endpoint, 'GET', params=params)

        except Exception as e:
            logger.error(f"Erro ao obter histórico: {e}")
            return {'success': False, 'error': str(e)}

    def send_bulk_messages(
        self,
        messages: List[Dict[str, Any]],
        default_chat_id_usuario: Optional[int] = None,
        default_session: Optional[str] = None
    ) -> Dict:
        """
        Envia múltiplas mensagens em lote com seleção de sessão por item.
        Cada item pode conter:
          - phone (str) [obrigatório]
          - message (str) [obrigatório]
          - chat_id_usuario (int) OU session (str) [opcional por item]
          - options (dict) [opcional]
        Se não vier, usa default_chat_id_usuario OU default_session (nessa ordem), caindo em self.default_session.
        """
        try:
            results = []
            success_count = 0
            error_count = 0

            for i, msg_data in enumerate(messages):
                phone = msg_data.get('phone')
                message = msg_data.get('message')
                per_item_chat_id = msg_data.get('chat_id_usuario', default_chat_id_usuario)
                per_item_session = msg_data.get('session', default_session)
                options = msg_data.get('options')

                if not phone or not message:
                    results.append({'index': i, 'phone': phone, 'success': False, 'error': 'Dados incompletos'})
                    error_count += 1
                    continue

                result = self.send_message(
                    phone,
                    message,
                    chat_id_usuario=per_item_chat_id,
                    session=per_item_session,
                    options=options
                )

                results.append({
                    'index': i,
                    'phone': phone,
                    'success': result.get('success', False),
                    'message_id': result.get('messageId'),
                    'error': result.get('error'),
                    'session': result.get('session')
                })

                if result.get('success'):
                    success_count += 1
                else:
                    error_count += 1

                if i < len(messages) - 1 and self.message_delay > 0:
                    time.sleep(self.message_delay)

            return {
                'success': True,
                'total': len(messages),
                'success_count': success_count,
                'error_count': error_count,
                'results': results
            }

        except Exception as e:
            logger.error(f"Erro no envio em lote: {e}")
            return {'success': False, 'error': str(e)}

    # ---------------------------
    # Saúde / Sessões
    # ---------------------------
    def health_check(self) -> Dict:
        """Checagem do servidor (global, sem sessão)."""
        try:
            return self._make_request(self._paths["health"], 'GET')
        except Exception as e:
            logger.error(f"Erro no health check: {e}")
            return {'success': False, 'error': str(e)}

    def get_sessions(self) -> Dict:
        """Lista as sessões disponíveis no servidor."""
        try:
            return self._make_request(self._paths["sessions"], 'GET')
        except Exception as e:
            logger.error(f"Erro ao obter sessões: {e}")
            return {'success': False, 'error': str(e)}

    # ---------------------------
    # Telefones
    # ---------------------------
    def _clean_phone_number(self, phone: str) -> str:
        """
        Limpa e formata número. Default: Brasil (55) se não vier DDI.
        Ajuste conforme sua regra de negócio.
        """
        if not phone:
            return ""
        clean = ''.join(filter(str.isdigit, phone))

        # já tem DDI BR
        if clean.startswith('55'):
            # Mantém como está; muitas impls aceitam 12-13 dígitos conforme DDD e 9º dígito
            return clean

        # sem DDI: adiciona BR por padrão se tiver ao menos 10 dígitos (DDD + número)
        if len(clean) >= 10:
            return f"55{clean}"

        return ""

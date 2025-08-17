"""
Integração corrigida para múltiplas sessões com Baileys API
Suporta sessão por usuário (ex.: user_{chat_id_usuario}) em TODOS os endpoints.
"""

import os
import requests
import logging
from datetime import datetime
import json
import time
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)

def formatar_datetime_br(dt: datetime) -> str:
    # fallback simples caso o util não esteja disponível
    return dt.strftime("%d/%m/%Y %H:%M")

class BaileysAPI:
    def __init__(self):
        """Inicializa a integração com Baileys API"""
        self.base_url = os.getenv('BAILEYS_API_URL', 'http://localhost:3000')
        self.api_key = os.getenv('BAILEYS_API_KEY', '')
        self.default_session = os.getenv('BAILEYS_SESSION', 'bot_clientes')  # fallback caso não seja informado chat_id
        self.timeout = int(os.getenv('BAILEYS_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('BAILEYS_MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('BAILEYS_RETRY_DELAY', '5'))

        # Config de envio
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

    # ---------------------------
    # Sessão / Helpers
    # ---------------------------
    def get_user_session(self, chat_id_usuario: Optional[int]) -> str:
        """Gera nome de sessão específico para o usuário"""
        if chat_id_usuario is None:
            return self.default_session
        return f"user_{chat_id_usuario}"

    def _resolve_session(self, chat_id_usuario: Optional[int] = None, explicit_session: Optional[str] = None) -> str:
        """Resolve a sessão a ser usada na chamada"""
        if explicit_session:
            return explicit_session
        return self.get_user_session(chat_id_usuario)

    # ---------------------------
    # HTTP Client com retry
    # ---------------------------
    def _make_request(self, endpoint: str, method: str = 'GET', data: Dict = None, retries: Optional[int] = None, params: Dict = None) -> Dict:
        """Faz requisição HTTP para a API Baileys"""
        if retries is None:
            retries = self.max_retries

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        for attempt in range(retries + 1):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=self.headers, timeout=self.timeout, params=params or data)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=self.headers, timeout=self.timeout, json=data, params=params)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=self.headers, timeout=self.timeout, json=data, params=params)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=self.headers, timeout=self.timeout, params=params)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")

                logger.debug(f"Baileys API Request: {method} {url} - Status: {response.status_code}")

                if 200 <= response.status_code < 300:
                    # permitir 204/201 etc.
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        return {'success': True, 'data': response.text or ''}
                elif response.status_code == 401:
                    return {'success': False, 'error': 'Não autorizado - verifique API Key'}
                elif response.status_code == 404:
                    return {'success': False, 'error': 'Endpoint não encontrado'}
                elif response.status_code == 429:
                    return {'success': False, 'error': 'Muitas requisições - tente mais tarde'}
                else:
                    error_msg = f"Erro HTTP {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', error_msg)
                    except Exception:
                        error_msg = response.text or error_msg

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
        """Obtém status da conexão WhatsApp para uma sessão específica"""
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            now = time.time()
            cache_key = f'status_{session_name}'
            if cache_key in self._status_cache and now - self._status_cache.get(f'{cache_key}_timestamp', 0) < self._cache_timeout:
                return self._status_cache[cache_key]

            response = self._make_request(f'status/{session_name}', 'GET')
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
            else:
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
        """Gera QR Code para sessão específica"""
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            response = self._make_request(f'qr/{session_name}', 'GET')
            if response.get('success'):
                data = response.get('data', response)  # alguns servers retornam dentro de data
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
    def send_message(self, phone: str, message: str, chat_id_usuario: Optional[int] = None, session: Optional[str] = None, options: Dict = None) -> Dict:
        """Envia mensagem via WhatsApp na sessão específica"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            payload = {'number': clean_phone, 'message': message}
            if options:
                payload.update(options)

            response = self._make_request(f'send-message/{session_name}', 'POST', payload)
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

    def send_image(self, phone: str, image_path: str, chat_id_usuario: Optional[int] = None, session: Optional[str] = None, caption: Optional[str] = None) -> Dict:
        """Envia imagem via WhatsApp na sessão específica"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            data = {'number': clean_phone, 'image': image_path}
            if caption:
                data['caption'] = caption

            response = self._make_request(f'send-image/{session_name}', 'POST', data)
            if response.get('success') and self.message_delay > 0:
                time.sleep(self.message_delay)
            return response

        except Exception as e:
            logger.error(f"Erro ao enviar imagem: {e}")
            return {'success': False, 'error': str(e)}

    def send_document(self, phone: str, document_path: str, filename: Optional[str] = None, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """Envia documento via WhatsApp na sessão específica"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            data = {'number': clean_phone, 'document': document_path}
            if filename:
                data['filename'] = filename

            response = self._make_request(f'send-document/{session_name}', 'POST', data)
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
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            session_name = self._resolve_session(chat_id_usuario, session)
            return self._make_request(f'chat-info/{session_name}/{clean_phone}', 'GET')
        except Exception as e:
            logger.error(f"Erro ao obter info do chat: {e}")
            return {'success': False, 'error': str(e)}

    def is_number_registered(self, phone: str, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            session_name = self._resolve_session(chat_id_usuario, session)
            data = {'number': clean_phone}
            return self._make_request(f'check-number/{session_name}', 'POST', data)
        except Exception as e:
            logger.error(f"Erro ao verificar número: {e}")
            return {'success': False, 'error': str(e)}

    def reconnect(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            response = self._make_request(f'restart/{session_name}', 'POST')
            # limpa cache da sessão
            self._status_cache.pop(f'status_{session_name}', None)
            self._status_cache.pop(f'status_{session_name}_timestamp', None)
            return response
        except Exception as e:
            logger.error(f"Erro ao reconectar: {e}")
            return {'success': False, 'error': str(e)}

    def logout(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            response = self._make_request(f'logout/{session_name}', 'POST')
            # limpa cache da sessão
            self._status_cache.pop(f'status_{session_name}', None)
            self._status_cache.pop(f'status_{session_name}_timestamp', None)
            return response
        except Exception as e:
            logger.error(f"Erro ao fazer logout: {e}")
            return {'success': False, 'error': str(e)}

    def get_config(self) -> Dict:
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

    def get_message_history(self, phone: str, limit: int = 50, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}
            session_name = self._resolve_session(chat_id_usuario, session)
            params = {'limit': limit}
            return self._make_request(f'messages/{session_name}/{clean_phone}', 'GET', params=params)
        except Exception as e:
            logger.error(f"Erro ao obter histórico: {e}")
            return {'success': False, 'error': str(e)}

    def send_bulk_messages(self, messages: List[Dict[str, Any]], default_chat_id_usuario: Optional[int] = None, default_session: Optional[str] = None) -> Dict:
        """
        Envia múltiplas mensagens em lote.
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

                result = self.send_message(phone, message, chat_id_usuario=per_item_chat_id, session=per_item_session, options=options)
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
        try:
            return self._make_request('health', 'GET')
        except Exception as e:
            logger.error(f"Erro no health check: {e}")
            return {'success': False, 'error': str(e)}

    def get_sessions(self) -> Dict:
        try:
            return self._make_request('sessions', 'GET')
        except Exception as e:
            logger.error(f"Erro ao obter sessões: {e}")
            return {'success': False, 'error': str(e)}

    # ---------------------------
    # Telefones
    # ---------------------------
    def _clean_phone_number(self, phone: str) -> str:
        """Limpa e formata número de telefone; prioriza BR (55) se não houver DDI."""
        if not phone:
            return ""
        clean = ''.join(filter(str.isdigit, phone))

        # se já vier com DDI
        if clean.startswith('55'):
            if len(clean) >= 12:  # 55 + DDD(2) + 9 dígitos
                return clean
            # se vier menor, ainda devolvemos para a API decidir; alternativa: validar melhor
            return clean

        # sem DDI: adiciona BR por padrão
        if len(clean) >= 10:
            return f"55{clean}"

        return ""

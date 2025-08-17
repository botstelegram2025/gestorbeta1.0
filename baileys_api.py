
"""
Baileys API client (multi-sessão, compatível com o servidor incluso em /baileys-server/server.js)
- Gera QR por sessão
- Envia mensagem por sessão (via body.session_id)
- Status/reconnect por sessão
- Endpoints não suportados no servidor atual retornam erro amigável
"""

import os
import requests
import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

def formatar_datetime_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")

class BaileysAPI:
    def __init__(self):
        self.base_url = os.getenv('BAILEYS_API_URL', 'http://localhost:3000')
        self.api_key = os.getenv('BAILEYS_API_KEY', '')
        self.default_session = os.getenv('BAILEYS_SESSION', 'bot_clientes')
        self.timeout = int(os.getenv('BAILEYS_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('BAILEYS_MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('BAILEYS_RETRY_DELAY', '5'))
        self.message_delay = int(os.getenv('BAILEYS_MESSAGE_DELAY', '1'))
        self.auto_reconnect = os.getenv('BAILEYS_AUTO_RECONNECT', 'true').lower() == 'true'

        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Bot-Clientes/1.0'
        }
        if self.api_key:
            self.headers['Authorization'] = f'Bearer {self.api_key}'

        self._status_cache: Dict[str, Any] = {}
        self._cache_timeout = 300  # 5min

        # Rotas do servidor atual (vide /baileys-server/server.js)
        self._paths = {
            "status":        "status/{session}",
            "qr":            "qr/{session}",            # também existe GET /qr?sessionId=
            "send_message":  "send-message",            # requer body.session_id
            "reconnect":     "reconnect/{session}",
            "health":        "health",
            "sessions":      "sessions",
            # Não suportados: send-image, send-document, check-number, messages, chat-info, logout
        }

        logger.info(f"Baileys API inicializada em {self.base_url} (sessão padrão: {self.default_session})")

    # --------------------- Helpers de sessão ---------------------
    def get_user_session(self, chat_id_usuario: Optional[int]) -> str:
        return self.default_session if chat_id_usuario is None else f"user_{chat_id_usuario}"

    def _resolve_session(self, chat_id_usuario: Optional[int] = None, explicit_session: Optional[str] = None) -> str:
        return explicit_session or self.get_user_session(chat_id_usuario)

    # --------------------- HTTP base com retry -------------------
    def _make_request(self, endpoint: str, method: str = 'GET', data: Dict = None, retries: Optional[int] = None, params: Dict = None) -> Dict:
        if retries is None:
            retries = self.max_retries
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        for attempt in range(retries + 1):
            try:
                if method == 'GET':
                    r = requests.get(url, headers=self.headers, timeout=self.timeout, params=params or data)
                elif method == 'POST':
                    r = requests.post(url, headers=self.headers, timeout=self.timeout, json=data, params=params)
                elif method == 'PUT':
                    r = requests.put(url, headers=self.headers, timeout=self.timeout, json=data, params=params)
                elif method == 'DELETE':
                    r = requests.delete(url, headers=self.headers, timeout=self.timeout, params=params)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")

                logger.debug(f"[BaileysAPI] {method} {url} -> {r.status_code}")

                if 200 <= r.status_code < 300:
                    try:
                        return r.json()
                    except json.JSONDecodeError:
                        return {'success': True, 'data': r.text or ''}
                elif r.status_code == 401:
                    return {'success': False, 'error': 'Não autorizado - verifique API Key'}
                elif r.status_code == 404:
                    return {'success': False, 'error': 'Endpoint não encontrado'}
                elif r.status_code == 429:
                    return {'success': False, 'error': 'Muitas requisições - tente mais tarde'}
                else:
                    try:
                        e = r.json()
                        msg = e.get('error', f"Erro HTTP {r.status_code}")
                    except Exception:
                        msg = r.text or f"Erro HTTP {r.status_code}"
                    if attempt < retries:
                        time.sleep(self.retry_delay)
                        continue
                    return {'success': False, 'error': msg}
            except requests.exceptions.ConnectionError:
                if attempt < retries:
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': 'Erro de conexão com Baileys API'}
            except requests.exceptions.Timeout:
                if attempt < retries:
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': 'Timeout na requisição para Baileys API'}
            except Exception as e:
                if attempt < retries:
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': f'Erro inesperado: {e}'}
        return {'success': False, 'error': 'Máximo de tentativas excedido'}

    # --------------------- Status/QR/Controle --------------------
    def get_status(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            now = time.time()
            cache_key = f'status_{session_name}'
            if cache_key in self._status_cache and now - self._status_cache.get(f'{cache_key}_timestamp', 0) < self._cache_timeout:
                return self._status_cache[cache_key]

            endpoint = self._paths["status"].format(session=session_name)
            resp = self._make_request(endpoint, 'GET')
            if resp.get('success'):
                data = resp.get('data', {})
                status = {
                    'status': self._format_connection_status((data or {}).get('state', 'disconnected')),
                    'numero': ((data or {}).get('user') or {}).get('id', '').replace('@s.whatsapp.net', ''),
                    'bateria': ((data or {}).get('battery') or {}).get('percentage'),
                    'ultima_conexao': self._format_last_seen((data or {}).get('lastSeen')),
                    'qr_needed': bool((data or {}).get('qr')),
                    'mensagens_enviadas': ((data or {}).get('stats') or {}).get('sent', 0),
                    'mensagens_falharam': ((data or {}).get('stats') or {}).get('failed', 0),
                    'fila_pendente': ((data or {}).get('stats') or {}).get('pending', 0),
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
                'error': resp.get('error', 'Erro desconhecido'),
                'session': session_name
            }
        except Exception as e:
            logger.error(f"Erro ao obter status: {e}")
            return {'status': '❌ Erro interno', 'error': str(e)}

    def generate_qr_code(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        """GET /qr/:sessionId (servidor também aceita /qr?sessionId=)"""
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["qr"].format(session=session_name)
            resp = self._make_request(endpoint, 'GET')
            if resp.get('success'):
                data = resp.get('data', resp)
                return {
                    'success': True,
                    'qr_code': data.get('qr'),
                    'qr_image': data.get('qr_image'),
                    'session': session_name,
                    'instructions': data.get('instructions', '')
                }
            return {'success': False, 'error': resp.get('error', 'QR Code não disponível'), 'session': session_name}
        except Exception as e:
            logger.error(f"Erro ao gerar QR Code: {e}")
            return {'success': False, 'error': str(e)}

    def reconnect(self, chat_id_usuario: Optional[int] = None, session: Optional[str] = None) -> Dict:
        try:
            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["reconnect"].format(session=session_name)
            self._status_cache.pop(f'status_{session_name}', None)
            self._status_cache.pop(f'status_{session_name}_timestamp', None)
            return self._make_request(endpoint, 'POST')
        except Exception as e:
            logger.error(f"Erro ao reconectar: {e}")
            return {'success': False, 'error': str(e)}

    # --------------------- Envio de mensagem ---------------------
    def send_message(self, phone: str, message: str, chat_id_usuario: Optional[int] = None, session: Optional[str] = None, options: Optional[Dict] = None) -> Dict:
        """POST /send-message (body: number, message, session_id)"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {'success': False, 'error': 'Número de telefone inválido'}

            session_name = self._resolve_session(chat_id_usuario, session)
            endpoint = self._paths["send_message"]
            payload = {'number': clean_phone, 'message': message, 'session_id': session_name}
            if options:
                payload.update(options)

            resp = self._make_request(endpoint, 'POST', payload)
            if resp.get('success'):
                if self.message_delay > 0:
                    time.sleep(self.message_delay)
                return {
                    'success': True,
                    'messageId': resp.get('messageId') or (resp.get('data') or {}).get('messageId'),
                    'timestamp': resp.get('timestamp', time.time()),
                    'session': session_name
                }
            return {'success': False, 'error': resp.get('error', 'Erro desconhecido'), 'session': session_name}
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return {'success': False, 'error': str(e)}

    # --------------------- Utilidades ----------------------------
    def health_check(self) -> Dict:
        try:
            return self._make_request(self._paths["health"], 'GET')
        except Exception as e:
            logger.error(f"Erro no health check: {e}")
            return {'success': False, 'error': str(e)}

    def get_sessions(self) -> Dict:
        try:
            return self._make_request(self._paths["sessions"], 'GET')
        except Exception as e:
            logger.error(f"Erro ao obter sessões: {e}")
            return {'success': False, 'error': str(e)}

    def get_config(self) -> Dict:
        return {
            'base_url': self.base_url,
            'default_session': self.default_session,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'message_delay': self.message_delay,
            'auto_reconnect': self.auto_reconnect,
            'api_key_configured': bool(self.api_key),
        }

    def update_config(self, **kwargs) -> bool:
        try:
            if 'timeout' in kwargs: self.timeout = int(kwargs['timeout'])
            if 'max_retries' in kwargs: self.max_retries = int(kwargs['max_retries'])
            if 'message_delay' in kwargs: self.message_delay = int(kwargs['message_delay'])
            if 'auto_reconnect' in kwargs: self.auto_reconnect = bool(kwargs['auto_reconnect'])
            if 'default_session' in kwargs: self.default_session = str(kwargs['default_session'])
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar configurações: {e}")
            return False

    # --------------------- Telefones -----------------------------
    def _clean_phone_number(self, phone: str) -> str:
        if not phone: return ""
        clean = ''.join(filter(str.isdigit, phone))
        if clean.startswith('55'):
            return clean
        if len(clean) >= 10:
            return f"55{clean}"
        return ""

    # --------------------- Formatação ----------------------------
    def _format_connection_status(self, state: str) -> str:
        return {
            'open': '🟢 Conectado',
            'connecting': '🟡 Conectando',
            'close': '🔴 Desconectado',
            'disconnected': '🔴 Desconectado'
        }.get(state, f'❓ {state}')

    def _format_last_seen(self, timestamp) -> str:
        if not timestamp: return 'Nunca'
        try:
            if isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp)
            else:
                dt = datetime.fromisoformat(str(timestamp))
            return formatar_datetime_br(dt)
        except Exception:
            return 'Inválido'

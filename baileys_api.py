"""
Integração com API Baileys para WhatsApp
Sistema de cobrança e envio de mensagens via WhatsApp Web
"""

import os
import requests
import logging
from datetime import datetime
import json
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

from utils import agora_br, formatar_datetime_br  # se já usa em outros lugares

logger = logging.getLogger(__name__)


class BaileysAPI:
    """
    Wrapper para a API Node do Baileys com persistência local.
    Endpoints esperados (servidor Node):
      GET  /status/:sessionId
      GET  /qr/:sessionId
      POST /send-message  { number, message, session_id }
      POST /reconnect/:sessionId
      POST /clear-session/:sessionId
      GET  /sessions
    """

    # prefixo de sessão por usuário
    SESSION_PREFIX = "user_"

    def __init__(self):
        """Inicializa a integração com Baileys API"""
        raw = os.getenv("BAILEYS_API_URL", "http://localhost:3000").strip()
        if not urlparse(raw).scheme:
            raw = "http://" + raw
        self.base_url = raw.rstrip("/")
        self.api_key = os.getenv("BAILEYS_API_KEY", "")
        self.timeout = int(os.getenv("BAILEYS_TIMEOUT", "30"))
        self.max_retries = int(os.getenv("BAILEYS_MAX_RETRIES", "3"))
        self.retry_delay = int(os.getenv("BAILEYS_RETRY_DELAY", "5"))
        self.message_delay = int(os.getenv("BAILEYS_MESSAGE_DELAY", "2"))
        self.auto_reconnect = os.getenv("BAILEYS_AUTO_RECONNECT", "true").lower() == "true"

        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Bot-Clientes/1.0",
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

        # cache simples de status
        self._status_cache: Dict[str, Any] = {}
        self._cache_timeout = 300  # 5 minutos

        logger.info(f"Baileys API inicializada: {self.base_url}")

    # ---------- helpers de sessão ----------
    def get_user_session(self, chat_id_usuario: int) -> str:
        """Gera nome de sessão específico para o usuário"""
        return f"{self.SESSION_PREFIX}{chat_id_usuario}"

    # ---------- HTTP genérico ----------
    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        retries: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Faz requisição HTTP resiliente à API Baileys"""
        if retries is None:
            retries = self.max_retries

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        for attempt in range(retries + 1):
            try:
                if method.upper() == "GET":
                    resp = requests.get(url, headers=self.headers, timeout=self.timeout, params=params or data)
                elif method.upper() == "POST":
                    resp = requests.post(url, headers=self.headers, timeout=self.timeout, json=data)
                elif method.upper() == "PUT":
                    resp = requests.put(url, headers=self.headers, timeout=self.timeout, json=data)
                elif method.upper() == "DELETE":
                    resp = requests.delete(url, headers=self.headers, timeout=self.timeout)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")

                logger.debug(f"[Baileys] {method} {url} -> {resp.status_code}")

                # respostas 2xx
                if 200 <= resp.status_code < 300:
                    try:
                        return resp.json()
                    except json.JSONDecodeError:
                        return {"success": True, "data": resp.text}

                # respostas de erro conhecidas
                if resp.status_code == 401:
                    return {"success": False, "error": "Não autorizado - verifique API Key"}
                if resp.status_code == 404:
                    return {"success": False, "error": "Endpoint não encontrado"}
                if resp.status_code == 429:
                    return {"success": False, "error": "Muitas requisições - tente mais tarde"}

                # demais erros: tentar novamente
                err_msg = ""
                try:
                    err_msg = resp.json().get("error")  # type: ignore
                except Exception:
                    err_msg = resp.text
                if attempt < retries:
                    logger.warning(f"[Baileys] Tentativa {attempt+1} falhou: {err_msg or resp.status_code}. Retry em {self.retry_delay}s")
                    time.sleep(self.retry_delay)
                    continue
                return {"success": False, "error": err_msg or f"HTTP {resp.status_code}"}

            except requests.exceptions.ConnectionError as e:
                if attempt < retries:
                    logger.warning(f"[Baileys] Conexão falhou (tentativa {attempt+1}): {e}. Retry em {self.retry_delay}s")
                    time.sleep(self.retry_delay)
                    continue
                return {"success": False, "error": "Erro de conexão com Baileys API"}
            except requests.exceptions.Timeout:
                if attempt < retries:
                    logger.warning(f"[Baileys] Timeout (tentativa {attempt+1}). Retry em {self.retry_delay}s")
                    time.sleep(self.retry_delay)
                    continue
                return {"success": False, "error": "Timeout na requisição para Baileys API"}
            except Exception as e:
                if attempt < retries:
                    logger.warning(f"[Baileys] Erro inesperado (tentativa {attempt+1}): {e}. Retry em {self.retry_delay}s")
                    time.sleep(self.retry_delay)
                    continue
                return {"success": False, "error": f"Erro inesperado: {e}"}

        return {"success": False, "error": "Máximo de tentativas excedido"}

    # ---------- API: STATUS ----------
    def get_status(self, chat_id_usuario: Optional[int] = None) -> Dict[str, Any]:
        """
        Obtém status da conexão WhatsApp para usuário específico.

        Servidor Node responde:
          {
            connected: bool,
            status: "connected"|"connecting"|"disconnected"|...,
            session: "5511...@s.whatsapp.net" | null,
            qr_available: bool,
            timestamp: "...",
            session_id: "user_123"
          }
        """
        try:
            session_name = self.get_user_session(chat_id_usuario) if chat_id_usuario else None
            if not session_name:
                return {
                    "status": "🔴 Sem sessão",
                    "numero": "N/A",
                    "qr_needed": True,
                    "connected": False,
                    "error": "chat_id_usuario não informado",
                }

            # cache
            now = time.time()
            cache_key = f"status_{session_name}"
            if cache_key in self._status_cache and now - self._status_cache.get(f"{cache_key}_ts", 0) < self._cache_timeout:
                return self._status_cache[cache_key]

            resp = self._make_request(f"status/{session_name}", "GET")
            # Em /status não há campo success — já vem o objeto de status
            if "connected" in resp and "status" in resp:
                connected = bool(resp.get("connected"))
                raw_status = str(resp.get("status") or "")
                numero_jid = resp.get("session")
                numero = (numero_jid or "").replace("@s.whatsapp.net", "")

                status_fmt = self._format_connection_status(raw_status, connected)
                data = {
                    "connected": connected,
                    "status": status_fmt,
                    "raw_status": raw_status,
                    "numero": numero or "N/A",
                    "qr_needed": bool(resp.get("qr_available")) and not connected,
                    "qr_available": bool(resp.get("qr_available")),
                    "session_id": resp.get("session_id", session_name),
                    "timestamp": resp.get("timestamp"),
                }

                # cache
                self._status_cache[cache_key] = data
                self._status_cache[f"{cache_key}_ts"] = now
                return data

            # caso a API responda um wrapper com success
            if resp.get("success") is False:
                return {
                    "connected": False,
                    "status": "🔴 Erro na conexão",
                    "numero": "N/A",
                    "qr_needed": True,
                    "error": resp.get("error", "Erro desconhecido"),
                }

            # fallback
            return {
                "connected": False,
                "status": "🔴 Indisponível",
                "numero": "N/A",
                "qr_needed": True,
                "error": "Resposta inválida da API de status",
            }

        except Exception as e:
            logger.error(f"Erro ao obter status: {e}")
            return {
                "connected": False,
                "status": "❌ Erro interno",
                "numero": "N/A",
                "qr_needed": True,
                "error": str(e),
            }

    def _format_connection_status(self, raw: str, connected: bool) -> str:
        raw = (raw or "").lower()
        if connected or raw == "connected":
            return "🟢 Conectado"
        if raw in ("connecting", "initializing"):
            return "🟡 Conectando"
        if raw in ("disconnected", "close", "error", "not_initialized"):
            return "🔴 Desconectado"
        return f"❓ {raw or 'desconhecido'}"

    # ---------- API: QR ----------
    def qr_code_needed(self, chat_id_usuario: int) -> bool:
        st = self.get_status(chat_id_usuario)
        return bool(st.get("qr_needed", True))

    def generate_qr_code(self, chat_id_usuario: int) -> Dict[str, Any]:
        """Gera QR Code (string e data URL) para a sessão do usuário"""
        try:
            session_name = self.get_user_session(chat_id_usuario)
            resp = self._make_request(f"qr/{session_name}", "GET")
            # servidor retorna { success, qr, qr_image, ... }
            if resp.get("success"):
                return {
                    "success": True,
                    "qr_code": resp.get("qr"),
                    "qr_image": resp.get("qr_image"),
                    "session": session_name,
                    "instructions": resp.get("instructions", ""),
                }
            return {"success": False, "error": resp.get("error", "QR Code não disponível")}
        except Exception as e:
            logger.error(f"Erro ao gerar QR Code: {e}")
            return {"success": False, "error": str(e)}

    # ---------- API: ENVIOS ----------
    def send_message(self, phone: str, message: str, chat_id_usuario: int, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Envia mensagem via WhatsApp do usuário específico"""
        try:
            clean_phone = self._clean_phone_number(phone)
            if not clean_phone:
                return {"success": False, "error": "Número de telefone inválido"}

            session_name = self.get_user_session(chat_id_usuario)
            payload = {
                "number": clean_phone,
                "message": message,
                "session_id": session_name,
            }
            if options:
                payload.update(options)

            resp = self._make_request("send-message", "POST", payload)
            if resp.get("success"):
                if self.message_delay > 0:
                    time.sleep(self.message_delay)
                return {
                    "success": True,
                    "messageId": resp.get("messageId"),
                    "timestamp": resp.get("timestamp", time.time()),
                }
            return {"success": False, "error": resp.get("error", "Falha no envio")}

        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return {"success": False, "error": str(e)}

    # (opcional) não suportado nativamente pelo servidor Node atual:
    def send_image(self, *args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "send_image não suportado neste servidor Baileys"}

    def send_document(self, *args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "send_document não suportado neste servidor Baileys"}

    def get_chat_info(self, *args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "get_chat_info não suportado neste servidor Baileys"}

    def is_number_registered(self, *args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "is_number_registered não suportado neste servidor Baileys"}

    def get_message_history(self, *args, **kwargs) -> Dict[str, Any]:
        return {"success": False, "error": "get_message_history não suportado neste servidor Baileys"}

    # ---------- API: CONEXÃO ----------
    def reconnect(self, chat_id_usuario: int) -> Dict[str, Any]:
        """Pede reconexão da sessão (sem apagar credenciais)"""
        try:
            session_name = self.get_user_session(chat_id_usuario)
            resp = self._make_request(f"reconnect/{session_name}", "POST")
            # limpar cache de status
            self._status_cache.clear()
            return resp
        except Exception as e:
            logger.error(f"Erro ao reconectar: {e}")
            return {"success": False, "error": str(e)}

    def clear_session(self, chat_id_usuario: int) -> Dict[str, Any]:
        """Apaga credenciais locais (força novo pareamento)"""
        try:
            session_name = self.get_user_session(chat_id_usuario)
            resp = self._make_request(f"clear-session/{session_name}", "POST")
            # limpar cache
            self._status_cache.clear()
            return resp
        except Exception as e:
            logger.error(f"Erro ao limpar sessão: {e}")
            return {"success": False, "error": str(e)}

    # compat: manter 'logout' chamando clear_session
    def logout(self, chat_id_usuario: int) -> Dict[str, Any]:
        return self.clear_session(chat_id_usuario)

    # ---------- API: ADMIN ----------
    def health_check(self) -> Dict[str, Any]:
        """Verifica se a API está funcionando (usa /sessions como health)"""
        try:
            resp = self._make_request("sessions", "GET")
            if isinstance(resp, dict) and "success" in resp:
                return {"success": bool(resp.get("success")), "data": resp}
            # caso responda sem chave success
            return {"success": True, "data": resp}
        except Exception as e:
            logger.error(f"Erro no health check: {e}")
            return {"success": False, "error": str(e)}

    def get_sessions(self) -> Dict[str, Any]:
        """Lista todas as sessões ativas"""
        try:
            return self._make_request("sessions", "GET")
        except Exception as e:
            logger.error(f"Erro ao obter sessões: {e}")
            return {"success": False, "error": str(e)}

    # ---------- Utilidades ----------
    def _clean_phone_number(self, phone: str) -> str:
        """Limpa e formata número de telefone para o formato aceito pelo servidor"""
        if not phone:
            return ""
        clean = "".join(ch for ch in phone if ch.isdigit())
        # com 55 (BR) e >= 12 dígitos está ok
        if clean.startswith("55") and len(clean) >= 12:
            return clean
        # se veio sem 55 mas >= 10 dígitos, prefixa 55
        if not clean.startswith("55") and len(clean) >= 10:
            return "55" + clean
        # fallback: se tem >= 10, retorna mesmo assim
        if len(clean) >= 10:
            return clean
        return ""

    # Compat: logging externo feito pelo caller
    def registrar_log_envio(
        self,
        cliente_id: int,
        template_id: Optional[int] = None,
        telefone: str = "",
        mensagem: str = "",
        tipo_envio: str = "manual",
        sucesso: bool = False,
        message_id: Optional[str] = None,
        erro: Optional[str] = None,
    ) -> bool:
        try:
            logger.info(f"Log de envio: cliente_id={cliente_id}, tel={telefone}, sucesso={sucesso}")
            if not sucesso and erro:
                logger.warning(f"Falha no envio para {telefone}: {erro}")
            return True
        except Exception as e:
            logger.error(f"Erro ao registrar log de envio: {e}")
            return False

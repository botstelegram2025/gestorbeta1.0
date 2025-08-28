
"""
bot_complete.py (condensado e funcional)
---------------------------------------
- Mantém as funcionalidades essenciais do original:
  • Isolamento por usuário (logs e fila) — admin vê tudo
  • Renovação de cliente: atualiza vencimento + cancela fila antiga + re‑agenda
  • Wrapper de registro de envio com suporte a chat_id_usuario
  • Exibição de logs por "tipo" (baileys / sistema / agendador), com fallback
  • Exibição de fila com filtro por dono, usando DB e/ou Scheduler
  • Envio de mensagens via self.bot (se disponível), com fallback para logs
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

try:
    import pytz
except Exception:  # pragma: no cover
    pytz = None  # timezone opcional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ===================== Utilidades =====================
def tz_sp():
    if pytz:
        return pytz.timezone('America/Sao_Paulo')
    return None  # fallback naive

def agora_br() -> datetime:
    tz = tz_sp()
    return datetime.now(tz) if tz else datetime.now()

def formatar_data_br(data_iso_yyyy_mm_dd: str) -> str:
    try:
        dt = datetime.fromisoformat(data_iso_yyyy_mm_dd)
    except Exception:
        try:
            dt = datetime.strptime(data_iso_yyyy_mm_dd, "%Y-%m-%d")
        except Exception:
            return data_iso_yyyy_mm_dd
    return dt.strftime("%d/%m/%Y")


# ===================== Núcleo do Bot =====================
class BotApp:
    def __init__(
        self,
        db: Any,
        scheduler: Any = None,
        bot: Any = None,
        admin_ids: Optional[Iterable[int]] = None,
    ) -> None:
        self.db = db
        self.scheduler = scheduler
        self.bot = bot
        self._admin_ids = set(admin_ids or [])

    # -------- Infra --------
    def is_admin(self, chat_id: int) -> bool:
        try:
            if hasattr(self.db, "is_admin"):
                return bool(self.db.is_admin(chat_id))
        except Exception:
            pass
        return chat_id in self._admin_ids

    def send_message(
        self, chat_id: int, text: str,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.bot and hasattr(self.bot, "send_message"):
            try:
                self.bot.send_message(
                    chat_id, text, parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                return
            except Exception as e:
                logger.warning(f"[send_message] falhou: {e}")
        logger.info(f"[MSG → {chat_id}] {text}")

    # -------- Registro de envios --------
    def registrar_envio(
        self,
        cliente_id: int,
        template_id: int,
        telefone: str,
        mensagem: str,
        tipo_envio: str,
        sucesso: bool,
        message_id: Optional[str] = None,
        erro: Optional[str] = None,
        chat_id_usuario: Optional[int] = None,
    ) -> None:
        """Wrapper que tenta incluir chat_id_usuario para isolamento."""
        try:
            if self.db and hasattr(self.db, "registrar_envio"):
                try:
                    self.db.registrar_envio(
                        cliente_id, template_id, telefone, mensagem,
                        tipo_envio, sucesso, message_id, erro,
                        chat_id_usuario=chat_id_usuario,
                    )
                except TypeError:
                    self.db.registrar_envio(
                        cliente_id, template_id, telefone, mensagem,
                        tipo_envio, sucesso, message_id, erro
                    )
            elif self.db and hasattr(self.db, "log_message"):
                self.db.log_message(cliente_id, template_id, telefone, mensagem, sucesso, erro)
            else:
                logger.info(
                    f"[REGISTRO ENVIO - fallback] cliente={cliente_id} "
                    f"sucesso={sucesso} tipo={tipo_envio} chat={chat_id_usuario}"
                )
        except Exception as e:
            logger.error(f"[registrar_envio] erro: {e}")

    # -------- Coleta e exibição de Logs --------
    def _fetch_logs(self, chat_id: int, tipo: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Tenta pegar logs já filtrados pelo DB; senão, aplica filtro em memória."""
        logs: List[Dict[str, Any]] = []
        try:
            if self.db and hasattr(self.db, "obter_logs_envios"):
                try:
                    logs = list(self.db.obter_logs_envios(limit=limit, chat_id_usuario=chat_id, tipo=tipo) or [])
                except TypeError:
                    logs = list(self.db.obter_logs_envios(limit=limit, chat_id_usuario=chat_id) or [])
            else:
                logs = []
        except Exception as e:
            logger.warning(f"Falha para obter logs no DB: {e}")
            logs = []
        if self.is_admin(chat_id) and not logs and self.db and hasattr(self.db, "obter_logs_envios"):
            try:
                logs = list(self.db.obter_logs_envios(limit=limit, tipo=tipo) or [])
            except TypeError:
                logs = list(self.db.obter_logs_envios(limit=limit) or [])
            except Exception:
                logs = []
        if not self.is_admin(chat_id):
            logs = [l for l in logs if self._log_pertence_ao_chat(l, chat_id)]
        return logs[:limit]

    def mostrar_logs(self, chat_id: int, tipo: str = "baileys", limit: int = 50) -> None:
        """Exibe logs por tipo ('baileys' | 'sistema' | 'agendador')."""
        logs = self._fetch_logs(chat_id, tipo=tipo, limit=limit)
        if not logs:
            self.send_message(chat_id, f"📜 *LOGS* — nenhum registro para este usuário.", parse_mode="Markdown")
            return

        linhas = [f"📜 *LOGS ({tipo.upper()})* — últimos {len(logs)}"]
        for log in logs:
            ok = log.get("sucesso")
            ic = "✅" if ok else "❌"
            dt = log.get("data_envio") or log.get("data") or "-"
            cli = log.get("cliente_nome") or "—"
            tel = log.get("telefone") or "—"
            tp = log.get("tipo") or log.get("tipo_envio") or "—"
            err = log.get("erro")
            linhas.append(f"{ic} {dt}\n👤 {cli} | 📱 {tel}\n📄 {tp}")
            if not ok and err:
                linhas.append(f"⚠️ {err}")
            linhas.append("")

        self.send_message(chat_id, "\n".join(linhas), parse_mode="Markdown")

    # -------- Fila (isolada por usuário) --------
    def mostrar_fila_mensagens(self, chat_id: int, limit: int = 50) -> None:
        """Mostra fila de mensagens agendadas; admin vê tudo."""
        itens: List[Dict[str, Any]] = []

        # 1) Preferir DB
        try:
            if self.db:
                if self.is_admin(chat_id):
                    try:
                        itens = list(self.db.obter_todas_mensagens_fila(limit=limit) or [])
                    except Exception:
                        itens = list(self.db.obter_mensagens_pendentes(limit=limit) or [])
                else:
                    try:
                        itens = list(self.db.obter_todas_mensagens_fila(limit=limit, chat_id_usuario=chat_id) or [])
                    except TypeError:
                        try:
                            itens = list(self.db.obter_mensagens_pendentes(limit=limit, chat_id_usuario=chat_id) or [])
                        except TypeError:
                            itens = list(self.db.obter_todas_mensagens_fila(limit=limit*3) or [])
        except Exception as e:
            logger.warning(f"Falha ao buscar fila no DB: {e}")
            itens = []

        # 2) Fallback: scheduler
        if not itens and self.scheduler and hasattr(self.scheduler, "obter_fila_mensagens"):
            try:
                itens = list(self.scheduler.obter_fila_mensagens() or [])
            except Exception as e:
                logger.warning(f"Falha ao buscar fila no scheduler: {e}")
                itens = []

        # 3) Isolamento por usuário em memória
        if not self.is_admin(chat_id):
            allowed_ids = set()
            try:
                clientes = list(self.db.listar_clientes(apenas_ativos=False, chat_id_usuario=chat_id) or [])
                allowed_ids = {c.get("id") for c in clientes if isinstance(c, dict) and c.get("id") is not None}
            except Exception:
                allowed_ids = set()

            def pertence(item: Dict[str, Any]) -> bool:
                if item.get("chat_id_usuario") == chat_id:
                    return True
                if item.get("cliente_chat_id_usuario") == chat_id:
                    return True
                cid = item.get("cliente_id")
                return cid in allowed_ids if cid is not None else False

            itens = [x for x in itens if isinstance(x, dict) and pertence(x)]

        def key_when(x: Dict[str, Any]):
            return x.get("agendado_para") or x.get("data") or ""

        itens.sort(key=key_when)

        if not itens:
            self.send_message(
                chat_id,
                "📋 *FILA DE MENSAGENS*\n\n🟢 Fila vazia para este usuário.",
                parse_mode="Markdown",
            )
            return

        linhas = [f"📋 *FILA PENDENTE* — mostrando até {min(limit, len(itens))}"]
        for item in itens[:limit]:
            alvo = item.get("agendado_para") or "—"
            cli = item.get("cliente_nome") or "—"
            tel = item.get("telefone") or "—"
            tp  = item.get("tipo_mensagem") or item.get("tipo") or "—"
            iid = item.get("id", "—")
            linhas.append(f"⏰ {alvo}\n👤 {cli}\n📱 {tel}\n📄 {tp}\n🆔 {iid}\n")

        if len(itens) > limit:
            linhas.append(f"... e mais {len(itens) - limit} mensagens.")

        self.send_message(chat_id, "\n".join(linhas), parse_mode="Markdown")

    # -------- Renovação (cancelar fila + reagendar) --------
    def renovar_cliente(
        self,
        chat_id: int,
        cliente_id: int,
        dias: Optional[int] = 30,
        nova_data_iso: Optional[str] = None,
    ) -> None:
        """Renova o cliente e garante consistência da fila (cancelar + re-agendar)."""
        try:
            if nova_data_iso:
                novo_venc = nova_data_iso
            else:
                novo_venc = (agora_br().date() + timedelta(days=int(dias or 30))).isoformat()

            atualizado = False
            if self.db:
                try:
                    if hasattr(self.db, "renovar_cliente"):
                        atualizado = bool(self.db.renovar_cliente(cliente_id, novo_vencimento=novo_venc))
                    elif hasattr(self.db, "atualizar_vencimento"):
                        atualizado = bool(self.db.atualizar_vencimento(cliente_id, novo_venc))
                    elif hasattr(self.db, "atualizar_cliente"):
                        atualizado = bool(self.db.atualizar_cliente(cliente_id, {"vencimento": novo_venc}))
                except TypeError:
                    try:
                        atualizado = bool(self.db.renovar_cliente(cliente_id, novo_venc))
                    except Exception:
                        atualizado = False

            if not atualizado:
                self.send_message(chat_id, "⚠️ Não foi possível atualizar o vencimento no banco.")
                return

            canceladas = 0
            if self.scheduler:
                try:
                    if hasattr(self.scheduler, "cancelar_mensagens_cliente_renovado"):
                        canceladas = int(self.scheduler.cancelar_mensagens_cliente_renovado(cliente_id) or 0)
                except Exception as e:
                    logger.warning(f"Falha ao cancelar fila de {cliente_id}: {e}")
                try:
                    if hasattr(self.scheduler, "agendar_mensagens_cliente"):
                        self.scheduler.agendar_mensagens_cliente(cliente_id)
                except Exception as e:
                    logger.warning(f"Falha ao re-agendar mensagens do cliente {cliente_id}: {e}")
            else:
                logger.warning("Scheduler não disponível — pulando cancelamento/reagendamento.")

            cliente = None
            try:
                cliente = self.db.buscar_cliente_por_id(cliente_id) if self.db else None
            except Exception:
                cliente = None
            nome = (cliente or {}).get("nome", "Cliente")

            self.send_message(
                chat_id,
                f"🔄 *Renovação processada*\n"
                f"👤 {nome}\n"
                f"📅 Novo vencimento: *{formatar_data_br(novo_venc)}*\n"
                f"🧹 Mensagens canceladas: {canceladas}\n"
                f"✅ Fila re-agendada.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"[renovar_cliente] erro: {e}")
            self.send_message(chat_id, f"❌ Erro na renovação: {e}")

    # -------- Auxiliares de filtro --------
    def _log_pertence_ao_chat(self, log: Dict[str, Any], chat_id: int) -> bool:
        dono = log.get("chat_id_usuario")
        if dono is not None:
            return dono == chat_id
        cid = log.get("cliente_id")
        if cid and self.db and hasattr(self.db, "buscar_cliente_por_id"):
            try:
                cliente = self.db.buscar_cliente_por_id(cid) or {}
                return cliente.get("chat_id_usuario") == chat_id
            except Exception:
                return False
        return False


if __name__ == "__main__":
    # Smoke test mínimo para garantir import e execução básica.
    class DummyDB:
        def __init__(self):
            self._clientes = {1: {"id": 1, "nome": "Alice", "chat_id_usuario": 111}}
            self._logs = []
            self._fila = []

        def is_admin(self, chat_id): return chat_id == 999
        def buscar_cliente_por_id(self, cid): return self._clientes.get(cid)
        def listar_clientes(self, apenas_ativos=False, chat_id_usuario=None):
            return [c for c in self._clientes.values() if chat_id_usuario in (None, c["chat_id_usuario"])]
        def registrar_envio(self, *args, **kwargs): self._logs.append({"args": args, "kwargs": kwargs})
        def obter_logs_envios(self, limit=50, chat_id_usuario=None, tipo=None): return []
        def atualizar_vencimento(self, cliente_id, novo_venc):
            if cliente_id in self._clientes:
                self._clientes[cliente_id]["vencimento"] = novo_venc
                return True
            return False
        def obter_todas_mensagens_fila(self, limit=50, chat_id_usuario=None): return list(self._fila)
        def obter_mensagens_pendentes(self, limit=50, chat_id_usuario=None): return list(self._fila)

    class DummyScheduler:
        def cancelar_mensagens_cliente_renovado(self, cliente_id): return 1
        def agendar_mensagens_cliente(self, cliente_id): return True
        def obter_fila_mensagens(self): return []

    db = DummyDB()
    sch = DummyScheduler()
    app = BotApp(db=db, scheduler=sch, bot=None, admin_ids=[999])
    app.mostrar_logs(chat_id=111, tipo="baileys")
    app.mostrar_fila_mensagens(chat_id=111)
    app.renovar_cliente(chat_id=111, cliente_id=1, dias=30)
    print("OK: módulo executado sem erros.")

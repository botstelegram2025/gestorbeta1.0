"""
Módulo de Configuração de Horários (com botões de edição)
- Armazena em JSON local para simplificar a integração
- Exibe inline keyboards para edição rápida
- Suporta horários personalizados e estados de conversa
- Callback data esperadas (exemplos):
    edit_horario_envio, edit_horario_verificacao, edit_horario_limpeza
    set_envio_HHMM, set_verificacao_HHMM, set_limpeza_HHMM
    horario_personalizado_envio, horario_personalizado_verificacao, horario_personalizado_limpeza
    config_horarios, status_jobs, recriar_jobs, reset_horarios_padrao, voltar_configs, menu_principal
"""

import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class ScheduleConfig:
    def __init__(self, bot):
        self.bot = bot
        self.config_file = "schedule_config.json"
        self.default_config = {
            "horario_envio": "09:00",
            "horario_verificacao": "10:00",
            "horario_limpeza": "23:59",
            "timezone": "America/Sao_Paulo",
        }
        self.config = self.load_config()

    # ====== compat aliases ======
    def config_horarios(self, chat_id): return self.config_horarios_menu(chat_id)
    def menu_horarios(self, chat_id):   return self.config_horarios_menu(chat_id)
    def horarios(self, chat_id):        return self.config_horarios_menu(chat_id)
    # ============================

    # ---------- storage ----------
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # merge com defaults
                    out = self.default_config.copy()
                    out.update(data or {})
                    return out
            except Exception as e:
                logger.error(f"Erro ao carregar config: {e}")
        return self.default_config.copy()

    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar config: {e}")

    # ---------- UI screens ----------
    def config_horarios_menu(self, chat_id):
        try:
            msg = (
                "⚙️ *Configurações de Horários*\n\n"
                f"📤 Envio: {self.config.get('horario_envio')}\n"
                f"🔎 Verificação: {self.config.get('horario_verificacao')}\n"
                f"🧹 Limpeza: {self.config.get('horario_limpeza')}\n\n"
                f"🕒 Agora: {datetime.now().strftime('%H:%M:%S')}"
            )
            kb = {
                'inline_keyboard': [
                    [
                        {'text': '🕘 Horário de Envio', 'callback_data': 'edit_horario_envio'},
                        {'text': '🕔 Horário Verificação', 'callback_data': 'edit_horario_verificacao'}
                    ],
                    [
                        {'text': '🕚 Horário Limpeza', 'callback_data': 'edit_horario_limpeza'}
                    ],
                    [
                        {'text': '🔄 Recriar Jobs', 'callback_data': 'recriar_jobs'},
                        {'text': '📊 Status Jobs', 'callback_data': 'status_jobs'}
                    ],
                    [
                        {'text': '🔄 Reset para Padrão', 'callback_data': 'reset_horarios_padrao'}
                    ],
                    [
                        {'text': '🔙 Voltar', 'callback_data': 'voltar_configs'},
                        {'text': '🏠 Menu Principal', 'callback_data': 'menu_principal'}
                    ]
                ]
            }
            self.bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logger.error(f"Erro ao mostrar configurações de horários: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar configurações de horários.")

    def edit_horario_envio(self, chat_id):
        try:
            atual = self.config.get('horario_envio')
            msg = (
                "📤 *ALTERAR HORÁRIO DE ENVIO*\n\n"
                f"⏰ Atual: `{atual}`\n\n"
                "Escolha uma opção ou insira um personalizado:"
            )
            populares = [
                ['09:00', '09:15', '12:00'],
                ['14:00', '16:00', '17:00'],
                ['17:28', '18:00', '18:10'],
                ['19:00', '20:00', '21:00']
            ]
            kb = {'inline_keyboard': []}
            for linha in populares:
                row = [{'text': f'🕐 {h}', 'callback_data': f'set_envio_{h.replace(":","")}'}
                       for h in linha]
                kb['inline_keyboard'].append(row)
            kb['inline_keyboard'].append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_envio'}])
            kb['inline_keyboard'].append([{'text': '🔙 Voltar', 'callback_data': 'config_horarios'}])
            self.bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=kb)
        except Exception as e:
            logger.error(f"Erro ao configurar horário de envio: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_verificacao(self, chat_id):
        try:
            atual = self.config.get('horario_verificacao')
            msg = (
                "🔔 *ALTERAR HORÁRIO DE VERIFICAÇÃO*\n\n"
                f"⏰ Atual: `{atual}`\n\n"
                "Escolha uma opção ou insira um personalizado:"
            )
            opcoes = [
                ['06:00', '07:00', '08:00'],
                ['09:00', '12:00', '15:00'],
                ['17:00', '18:00', '19:00'],
                ['20:00', '21:00', '22:00']
            ]
            kb = {'inline_keyboard': []}
            for linha in opcoes:
                row = [{'text': f'🕐 {h}', 'callback_data': f'set_verificacao_{h.replace(":","")}'}
                       for h in linha]
                kb['inline_keyboard'].append(row)
            kb['inline_keyboard'].append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_verificacao'}])
            kb['inline_keyboard'].append([{'text': '🔙 Voltar', 'callback_data': 'config_horarios'}])
            self.bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=kb)
        except Exception as e:
            logger.error(f"Erro ao configurar horário de verificação: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    def edit_horario_limpeza(self, chat_id):
        try:
            atual = self.config.get('horario_limpeza')
            msg = (
                "🧹 *ALTERAR HORÁRIO DE LIMPEZA*\n\n"
                f"⏰ Atual: `{atual}`\n\n"
                "Escolha uma opção ou insira um personalizado:"
            )
            horarios = ['01:00', '02:00', '03:00', '04:00', '05:00', '23:00', '00:00']
            kb = {'inline_keyboard': []}
            for i in range(0, len(horarios), 3):
                row = []
                for j in range(3):
                    if i + j < len(horarios):
                        h = horarios[i + j]
                        row.append({'text': h, 'callback_data': f'set_limpeza_{h.replace(":","")}'})
                kb['inline_keyboard'].append(row)
            kb['inline_keyboard'].append([{'text': '⌨️ Horário Personalizado', 'callback_data': 'horario_personalizado_limpeza'}])
            kb['inline_keyboard'].append([{'text': '🔙 Voltar', 'callback_data': 'config_horarios'}])
            self.bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=kb)
        except Exception as e:
            logger.error(f"Erro ao configurar horário de limpeza: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao configurar horário.")

    # ---------- setters ----------
    def _validar_hhmm(self, texto):
        return bool(re.match(r'^([0-1][0-9]|2[0-3]):([0-5][0-9])$', texto or ''))

    def set_horario_envio(self, chat_id, novo_hhmm_digits):
        try:
            hh, mm = int(novo_hhmm_digits[:2]), int(novo_hhmm_digits[2:])
            valor = f"{hh:02d}:{mm:02d}"
            self.config['horario_envio'] = valor
            self.save_config()
            self.bot.send_message(chat_id, f"✅ Horário de *envio* alterado para `{valor}`", parse_mode='Markdown')
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de envio: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_verificacao(self, chat_id, novo_hhmm_digits):
        try:
            hh, mm = int(novo_hhmm_digits[:2]), int(novo_hhmm_digits[2:])
            valor = f"{hh:02d}:{mm:02d}"
            self.config['horario_verificacao'] = valor
            self.save_config()
            self.bot.send_message(chat_id, f"✅ Horário de *verificação* alterado para `{valor}`", parse_mode='Markdown')
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de verificação: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    def set_horario_limpeza(self, chat_id, novo_hhmm_digits):
        try:
            hh, mm = int(novo_hhmm_digits[:2]), int(novo_hhmm_digits[2:])
            valor = f"{hh:02d}:{mm:02d}"
            self.config['horario_limpeza'] = valor
            self.save_config()
            self.bot.send_message(chat_id, f"✅ Horário de *limpeza* alterado para `{valor}`", parse_mode='Markdown')
            self.config_horarios_menu(chat_id)
            self._reprogramar_jobs_seguro()
        except Exception as e:
            logger.error(f"Erro ao definir horário de limpeza: {e}")
            self.bot.send_message(chat_id, f"❌ Erro ao alterar horário: {e}")

    # ---------- personalizados ----------
    def horario_personalizado_envio(self, chat_id):
        self.bot.conversation_states[chat_id] = 'aguardando_horario_envio'
        self.bot.send_message(chat_id, "⌨️ Envie o novo horário de *envio* no formato HH:MM", parse_mode='Markdown',
                              reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]})

    def horario_personalizado_verificacao(self, chat_id):
        self.bot.conversation_states[chat_id] = 'aguardando_horario_verificacao'
        self.bot.send_message(chat_id, "⌨️ Envie o novo horário de *verificação* no formato HH:MM", parse_mode='Markdown',
                              reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]})

    def horario_personalizado_limpeza(self, chat_id):
        self.bot.conversation_states[chat_id] = 'aguardando_horario_limpeza'
        self.bot.send_message(chat_id, "⌨️ Envie o novo horário de *limpeza* no formato HH:MM", parse_mode='Markdown',
                              reply_markup={'inline_keyboard': [[{'text': '❌ Cancelar', 'callback_data': 'config_horarios'}]]})

    def processar_horario_personalizado(self, chat_id, texto, estado=None):
        try:
            if not self._validar_hhmm(texto):
                self.bot.send_message(chat_id, "❌ Formato inválido. Use HH:MM (ex.: 09:30). Tente novamente:")
                return False
            estado = estado or self.bot.conversation_states.get(chat_id)
            hhmm_digits = texto.replace(':', '')
            if estado == 'aguardando_horario_envio':
                self.set_horario_envio(chat_id, hhmm_digits)
            elif estado == 'aguardando_horario_verificacao':
                self.set_horario_verificacao(chat_id, hhmm_digits)
            elif estado == 'aguardando_horario_limpeza':
                self.set_horario_limpeza(chat_id, hhmm_digits)
            else:
                self.bot.send_message(chat_id, "❌ Estado inválido. Volte ao menu de horários.")
                return False
            self.bot.conversation_states.pop(chat_id, None)
            return True
        except Exception as e:
            logger.error(f"Erro ao processar horário personalizado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao processar horário personalizado.")
            return False

    # ---------- jobs (stubs) ----------
    def _reprogramar_jobs_seguro(self):
        """Stub: chame seu scheduler real aqui se tiver um wrapper."""
        try:
            if hasattr(self.bot, 'scheduler') and hasattr(self.bot.scheduler, '_setup_main_jobs'):
                self.bot.scheduler._setup_main_jobs()
                if not getattr(self.bot.scheduler, 'running', False):
                    self.bot.scheduler.start()
        except Exception as e:
            logger.warning(f"Falha ao reprogramar jobs (stub): {e}")


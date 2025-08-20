import json
import logging
import os

class ScheduleConfig:
    def __init__(self, bot):
        self.bot = bot
        self.config_file = "schedule_config.json"
        self.default_config = {
            "horario_envio": "09:00",
            "horario_verificacao": "10:00",
            "horario_limpeza": "23:59"
        }
        self.config = self.load_config()

    # ---- Aliases de compatibilidade ----
    def config_horarios(self, chat_id):
        return self.config_horarios_menu(chat_id)

    def menu_horarios(self, chat_id):
        return self.config_horarios_menu(chat_id)

    def horarios(self, chat_id):
        return self.config_horarios_menu(chat_id)
    # ------------------------------------

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Erro ao carregar config: {e}")
        return self.default_config.copy()

    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Erro ao salvar config: {e}")

    def config_horarios_menu(self, chat_id):
        try:
            msg = (
                "⚙️ *Configurações de Horários*\n\n"
                f"📤 Envio: {self.config.get('horario_envio')}\n"
                f"🔍 Verificação: {self.config.get('horario_verificacao')}\n"
                f"🧹 Limpeza: {self.config.get('horario_limpeza')}"
            )
            self.bot.send_message(chat_id, msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Erro ao mostrar configurações de horários: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao carregar configurações de horários.")

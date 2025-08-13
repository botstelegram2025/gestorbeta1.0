#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sistema de Limpeza da Conexão Baileys - Replit Edition
Evita problemas persistentes de QR code após atualizações
"""

import os
import logging
import requests
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class BaileysCleaner:
    """Classe para gerenciar limpeza da conexão Baileys"""
    
    def __init__(self, baileys_url="http://localhost:3000"):
        self.baileys_url = baileys_url.rstrip('/')
        
    def clear_session(self):
        """Limpa a sessão atual do Baileys"""
        try:
            logger.info("Limpando sessão do Baileys...")
            
            # Tentar parar a conexão atual
            response = requests.post(f"{self.baileys_url}/logout", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Logout realizado com sucesso")
            else:
                logger.warning(f"⚠️ Logout falhou com status {response.status_code}")
            
            # Limpar estado interno
            response = requests.post(f"{self.baileys_url}/clear", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Estado interno limpo")
            else:
                logger.warning(f"⚠️ Limpeza de estado falhou com status {response.status_code}")
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao limpar sessão: {e}")
            return False
    
    def restart_connection(self):
        """Reinicia a conexão do Baileys"""
        try:
            logger.info("Reiniciando conexão do Baileys...")
            
            # Primeiro limpar
            self.clear_session()
            
            # Aguardar um pouco
            import time
            time.sleep(2)
            
            # Reiniciar conexão
            response = requests.post(f"{self.baileys_url}/restart", timeout=15)
            if response.status_code == 200:
                logger.info("✅ Conexão reiniciada")
                return True
            else:
                logger.warning(f"⚠️ Reinício falhou com status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro ao reiniciar conexão: {e}")
            return False
    
    def get_status(self):
        """Obtém status atual da conexão"""
        try:
            response = requests.get(f"{self.baileys_url}/status", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "error", "code": response.status_code}
                
        except Exception as e:
            logger.error(f"Erro ao obter status: {e}")
            return {"status": "error", "error": str(e)}
    
    def force_new_qr(self):
        """Força geração de novo QR code"""
        try:
            logger.info("Forçando novo QR code...")
            
            # Limpar sessão primeiro
            self.clear_session()
            
            # Aguardar
            import time
            time.sleep(3)
            
            # Solicitar novo QR
            response = requests.get(f"{self.baileys_url}/qr", timeout=15)
            if response.status_code == 200:
                logger.info("✅ Novo QR code solicitado")
                return True
            else:
                logger.warning(f"⚠️ Falha ao gerar QR: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro ao gerar novo QR: {e}")
            return False
#!/usr/bin/env python3
"""
Script para corrigir isolamento de templates no bot_complete.py
Substitui todas as chamadas que não passam chat_id_usuario
"""

import re

def fix_template_isolation():
    # Ler o arquivo
    with open('bot_complete.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Padrões a corrigir
    fixes = [
        # listar_templates() -> listar_templates(chat_id_usuario=chat_id)
        (r'\.listar_templates\(\)(?!\s*if)', '.listar_templates(chat_id_usuario=chat_id)'),
        
        # buscar_template_por_id(template_id) -> buscar_template_por_id(template_id, chat_id_usuario=chat_id)
        (r'\.buscar_template_por_id\(([^)]+)\)(?!\s*if)', r'.buscar_template_por_id(\1, chat_id_usuario=chat_id)'),
        
        # obter_template(template_id) -> obter_template(template_id, chat_id_usuario=chat_id)  
        (r'\.obter_template\(([^)]+)\)(?!\s*if)', r'.obter_template(\1, chat_id_usuario=chat_id)'),
        
        # template_manager.listar_templates() if -> template_manager.listar_templates(chat_id_usuario=chat_id) if
        (r'template_manager\.listar_templates\(\)\s+if', 'template_manager.listar_templates(chat_id_usuario=chat_id) if'),
        
        # Corrigir duplicatas que podem ter sido criadas
        (r'chat_id_usuario=chat_id, chat_id_usuario=chat_id', 'chat_id_usuario=chat_id'),
        (r'template_id, chat_id_usuario=chat_id, chat_id_usuario=chat_id', 'template_id, chat_id_usuario=chat_id')
    ]
    
    # Aplicar correções
    for pattern, replacement in fixes:
        content = re.sub(pattern, replacement, content)
    
    # Casos especiais que precisam de contexto específico
    special_fixes = [
        # Corrigir cases onde não temos chat_id disponível mas o método está em uma função que tem
        ('def listar_templates_menu(self, chat_id', True),
        ('def menu_templates(self, chat_id', True),
        ('def processar_renovacao', True),
        ('def enviar_mensagem_cliente(self, chat_id', True),
        ('def menu_envio_massa(self, chat_id', True)
    ]
    
    # Salvar se houver mudanças
    if content != original_content:
        with open('bot_complete.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Correções de isolamento aplicadas!")
        return True
    else:
        print("ℹ️  Nenhuma correção necessária")
        return False

if __name__ == "__main__":
    fix_template_isolation()
#!/usr/bin/env python3
"""
Corrigir todas as chamadas no bot_complete.py para incluir isolamento por usuário
"""

import re

def fix_database_calls():
    """Corrigir todas as chamadas de banco de dados para incluir chat_id_usuario"""
    
    with open('bot_complete.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Padrões de chamadas que precisam ser corrigidas
    patterns = [
        # buscar_cliente_por_id sem usuário
        (r'self\.db\.buscar_cliente_por_id\(([^)]+)\)',
         r'self.db.buscar_cliente_por_id(\1, chat_id_usuario=chat_id)'),
        
        # buscar_cliente_por_telefone sem usuário
        (r'self\.db\.buscar_cliente_por_telefone\(([^)]+)\)',
         r'self.db.buscar_cliente_por_telefone(\1, chat_id_usuario=chat_id)'),
    ]
    
    # Aplicar correções
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    # Escrever arquivo corrigido
    with open('bot_complete.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Correções de chamadas de banco aplicadas")

def main():
    fix_database_calls()
    print("🎉 Todas as correções aplicadas!")

if __name__ == "__main__":
    main()
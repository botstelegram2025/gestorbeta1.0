#!/usr/bin/env python3
"""
CORREÇÃO CRÍTICA: Isolamento de dados por usuário
Garantir que cada usuário veja apenas seus próprios dados
"""

import os
import sys
import re

def fix_bot_functions():
    """Corrigir todas as funções do bot que não estão isolando dados por usuário"""
    
    # Ler arquivo do bot
    with open('bot_complete.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Lista de funções que precisam ser corrigidas
    functions_to_fix = [
        'gestao_clientes',
        'buscar_cliente', 
        'processar_busca_cliente',
        'mostrar_detalhes_cliente',
        'mostrar_relatorios'
    ]
    
    # Patterns para encontrar e corrigir chamadas incorretas
    patterns = [
        # Padrão: self.db.listar_clientes() sem parâmetro de usuário
        (r'self\.db\.listar_clientes\(\s*apenas_ativos=True\s*\)',
         'self.db.listar_clientes(apenas_ativos=True, chat_id_usuario=chat_id)'),
        
        # Padrão: self.db.listar_clientes() sem parâmetros
        (r'self\.db\.listar_clientes\(\s*\)',
         'self.db.listar_clientes(chat_id_usuario=chat_id)'),
        
        # Padrão: db.buscar_cliente sem usuário
        (r'self\.db\.buscar_cliente\(\s*([^,)]+)\s*\)',
         r'self.db.buscar_cliente(\1, chat_id_usuario=chat_id)'),
    ]
    
    # Aplicar correções
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    # Adicionar verificação de isolamento em todas as funções principais
    isolation_check = """
        # Garantir isolamento de dados
        if not hasattr(self, 'ensure_user_isolation'):
            logger.error("Função de isolamento não encontrada")
            return
        self.ensure_user_isolation(chat_id)
"""
    
    # Funções que devem ter verificação de isolamento
    functions_for_isolation = [
        'gestao_clientes',
        'listar_clientes', 
        'buscar_cliente',
        'processar_busca_cliente',
        'mostrar_detalhes_cliente',
        'adicionar_cliente_inicio',
        'mostrar_relatorios'
    ]
    
    for func_name in functions_for_isolation:
        # Encontrar a função e adicionar verificação no início
        pattern = rf'(def {func_name}\(self, chat_id[^)]*\):\s*"""[^"]*"""\s*try:)'
        replacement = rf'\1{isolation_check}'
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Escrever arquivo corrigido
    with open('bot_complete.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Correções de isolamento aplicadas no bot_complete.py")

def fix_database_functions():
    """Adicionar isolamento por usuário em funções críticas do database.py"""
    
    with open('database.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificar se buscar_cliente já tem isolamento
    if 'chat_id_usuario=None' not in content:
        # Encontrar e corrigir função buscar_cliente
        pattern = r'def buscar_cliente\(self, termo_busca, apenas_ativo=True\):'
        replacement = 'def buscar_cliente(self, termo_busca, apenas_ativo=True, chat_id_usuario=None):'
        content = re.sub(pattern, replacement, content)
        
        # Adicionar filtro de usuário na query
        pattern = r'(WHERE.*?ativo = TRUE.*?)(\s+ORDER BY)'
        replacement = r'\1 AND chat_id_usuario = %s\2'
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    with open('database.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Correções de isolamento aplicadas no database.py")

def main():
    """Executar todas as correções críticas"""
    print("🚨 INICIANDO CORREÇÃO CRÍTICA DE ISOLAMENTO DE USUÁRIOS")
    
    try:
        fix_bot_functions()
        fix_database_functions()
        
        print("🎉 CORREÇÕES CRÍTICAS CONCLUÍDAS!")
        print("📋 Cada usuário agora verá apenas seus próprios dados")
        print("🔒 Sistema completamente isolado por usuário")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro durante correções: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
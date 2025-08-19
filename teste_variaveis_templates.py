#!/usr/bin/env python3
"""
Script de teste para verificar o reconhecimento de variáveis de empresa nos templates
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import DatabaseManager
from templates import TemplateManager
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def testar_variaveis_empresa():
    """Testa se as variáveis de empresa estão sendo reconhecidas nos templates"""
    
    print("🧪 TESTE: Verificação de Variáveis de Templates")
    print("=" * 60)
    
    try:
        # Inicializar managers
        db = DatabaseManager()
        template_manager = TemplateManager(db)
        
        print("✅ Managers inicializados")
        
        # 1. Verificar configurações cadastradas no banco
        print("\n📊 CONFIGURAÇÕES NO BANCO:")
        print("-" * 30)
        
        configuracoes_teste = [
            'empresa_nome',
            'empresa_telefone', 
            'empresa_email',
            'pix_chave',
            'pix_beneficiario',
            'suporte_telefone'
        ]
        
        config_encontradas = {}
        for config in configuracoes_teste:
            valor = db.obter_configuracao(config, '[NÃO CONFIGURADO]')
            config_encontradas[config] = valor
            status = "✅" if valor != '[NÃO CONFIGURADO]' else "❌"
            print(f"{status} {config}: {valor}")
        
        # 2. Verificar variáveis disponíveis no TemplateManager
        print("\n🔧 VARIÁVEIS DISPONÍVEIS NO SISTEMA:")
        print("-" * 40)
        
        variaveis = template_manager.obter_variaveis_disponíveis()
        for var, desc in variaveis.items():
            if any(keyword in var for keyword in ['empresa', 'pix', 'suporte']):
                print(f"✅ {{{var}}} - {desc}")
        
        # 3. Criar template de teste
        print("\n📝 TESTE DE TEMPLATE:")
        print("-" * 25)
        
        template_teste = """🏢 Olá {nome}!

Sua conta de {pacote} vence em {vencimento}.
Valor: R$ {valor}

📱 Empresa: {empresa_nome}
☎️ Telefone: {empresa_telefone}  
📧 Email: {empresa_email}
🆘 Suporte: {suporte_telefone}

💰 PIX para pagamento:
🔑 Chave: {pix_chave}
👤 Beneficiário: {pix_beneficiario}

Obrigado!"""
        
        print("Template de teste criado:")
        print(template_teste)
        
        # 4. Dados de teste do cliente
        cliente_teste = {
            'nome': 'João da Silva',
            'telefone': '11999999999',
            'pacote': 'Netflix Premium',
            'valor': 45.90,
            'vencimento': '2024-12-25',
            'dias_vencimento': 5
        }
        
        # 5. Processar template
        print("\n🔄 PROCESSANDO TEMPLATE:")
        print("-" * 30)
        
        template_processado = template_manager.processar_template(
            template_teste, 
            cliente_teste
        )
        
        print("RESULTADO:")
        print(template_processado)
        
        # 6. Verificar se variáveis foram substituídas
        print("\n🔍 VERIFICAÇÃO DE SUBSTITUIÇÃO:")
        print("-" * 35)
        
        variaveis_empresa_testadas = [
            'empresa_nome', 'empresa_telefone', 'empresa_email',
            'pix_chave', 'pix_beneficiario', 'suporte_telefone'
        ]
        
        todas_substituidas = True
        for var in variaveis_empresa_testadas:
            placeholder = f"{{{var}}}"
            if placeholder in template_processado:
                print(f"❌ {var}: NÃO substituída (ainda aparece como {placeholder})")
                todas_substituidas = False
            else:
                valor_config = config_encontradas.get(var, '[NÃO ENCONTRADO]')
                if valor_config in template_processado:
                    print(f"✅ {var}: substituída corretamente → {valor_config}")
                else:
                    print(f"⚠️ {var}: substituída, mas valor não encontrado no resultado")
        
        # 7. Resultado final
        print("\n" + "=" * 60)
        if todas_substituidas:
            print("🎉 SUCESSO: Todas as variáveis de empresa foram substituídas!")
        else:
            print("🚨 PROBLEMA: Algumas variáveis não foram substituídas")
            print("   Verifique se as configurações estão cadastradas no banco")
        
        return todas_substituidas
        
    except Exception as e:
        print(f"❌ ERRO no teste: {e}")
        import traceback
        traceback.print_exc()
        return False

def testar_preview_template():
    """Testa a função de preview de template"""
    print("\n🎭 TESTE DE PREVIEW:")
    print("-" * 25)
    
    try:
        db = DatabaseManager()
        template_manager = TemplateManager(db)
        
        template_exemplo = """Olá {nome}!

🏢 {empresa_nome}
📞 {empresa_telefone}
💰 PIX: {pix_chave}
👤 {pix_beneficiario}"""
        
        preview = template_manager.gerar_preview_template(template_exemplo, usar_dados_exemplo=True)
        
        print("PREVIEW GERADO:")
        print(preview)
        
        # Verificar se dados de exemplo foram usados
        if "João Silva" in preview and "Streaming Premium" in preview:
            print("✅ Preview funcionando com dados de exemplo")
            return True
        else:
            print("❌ Preview não está usando dados de exemplo corretamente")
            return False
            
    except Exception as e:
        print(f"❌ ERRO no preview: {e}")
        return False

if __name__ == "__main__":
    print("🚀 INICIANDO TESTES DE VARIÁVEIS DE TEMPLATES")
    print("=" * 60)
    
    # Teste principal
    resultado_principal = testar_variaveis_empresa()
    
    # Teste de preview
    resultado_preview = testar_preview_template()
    
    print("\n" + "=" * 60)
    print("📋 RESUMO DOS TESTES:")
    print(f"✅ Variáveis de empresa: {'SUCESSO' if resultado_principal else 'FALHOU'}")
    print(f"✅ Preview de template: {'SUCESSO' if resultado_preview else 'FALHOU'}")
    
    if resultado_principal and resultado_preview:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("   Sistema de templates funcionando corretamente")
    else:
        print("\n🚨 ALGUNS TESTES FALHARAM!")
        print("   Verificar configurações e implementação")
# 📚 GUIA COMPLETO DO USUÁRIO
## Sistema de Gestão de Clientes WhatsApp/Telegram

---

## 🚀 INTRODUÇÃO

Este sistema automatiza a gestão de clientes e envio de mensagens via WhatsApp. Com ele você pode:
- Cadastrar e gerenciar clientes
- Criar templates de mensagens personalizados
- Enviar mensagens automáticas no vencimento
- Gerar relatórios detalhados
- Conectar WhatsApp para envios

---

## 📱 1. CONECTANDO O WHATSAPP

### Passo 1: Acessar Configuração WhatsApp
1. No menu principal, clique em **📱 WhatsApp**
2. Escolha **📱 Configurar WhatsApp**

### Passo 2: Gerar QR Code
1. O sistema irá gerar um QR Code
2. Abra o WhatsApp no seu celular
3. Vá em **Menu** → **Dispositivos Conectados** → **Conectar um dispositivo**
4. Aponte a câmera para o QR Code mostrado na tela

### Passo 3: Confirmar Conexão
- Aguarde até aparecer "✅ WhatsApp conectado com sucesso!"
- O sistema estará pronto para enviar mensagens

**⚠️ IMPORTANTE:**
- Mantenha o celular conectado à internet
- Não desconecte o WhatsApp Web manualmente
- Se desconectar, repita o processo

---

## 👥 2. CADASTRANDO CLIENTES

### Passo 1: Acessar Gestão de Clientes
1. No menu principal, clique em **👥 Gestão de Clientes**
2. Escolha **➕ Cadastrar Cliente**

### Passo 2: Preencher Dados
**Informe em ordem:**
1. **Nome completo** do cliente
2. **Telefone** (apenas números, ex: 11987654321)
3. **Data de vencimento** (formato: dd/mm/aaaa)
4. **Valor mensal** (ex: 50.00)
5. **Plano/serviço** (ex: "Plano Premium")

### Passo 3: Configurações Opcionais
- **Receber mensagens automáticas**: Sim/Não
- **Observações**: Informações extras sobre o cliente

### Passo 4: Confirmar Cadastro
- Revise todos os dados
- Clique em **✅ Confirmar**
- Cliente será cadastrado e aparecerá na lista

**💡 DICAS:**
- Telefone deve ter DDD + número (11 dígitos total)
- Data de vencimento define quando receberá cobrança
- Valor pode ser alterado depois se necessário

---

## 📄 3. CRIANDO TEMPLATES DE MENSAGENS

### Passo 1: Acessar Templates
1. No menu principal, clique em **⚙️ Configurações**
2. Escolha **📄 Templates**
3. Clique em **➕ Criar Template**

### Passo 2: Tipos de Templates

#### 🔴 Template de Cobrança (1 dia após vencimento)
**Uso:** Enviado automaticamente 1 dia após vencimento
**Exemplo:**
```
🔔 Olá {nome}!

Seu plano venceu ontem ({vencimento}). 
Para manter os serviços ativos, efetue o pagamento de R$ {valor}.

PIX: sua-chave-pix@email.com
Valor: R$ {valor}

Dúvidas? Entre em contato!
```

#### 💰 Template de Renovação
**Uso:** Para envios manuais ou renovações
**Exemplo:**
```
🎉 Olá {nome}!

Hora de renovar seu plano!
Vencimento: {vencimento}
Valor: R$ {valor}

Renove agora e continue aproveitando todos os benefícios!
```

#### ⚠️ Template de Aviso
**Uso:** Avisos gerais ou lembretes
**Exemplo:**
```
📢 {nome}, informativo importante!

Seu plano ({plano}) vence em breve: {vencimento}

Antecipe o pagamento e evite interrupções!
Valor: R$ {valor}
```

### Passo 3: Variáveis Disponíveis
Use estas variáveis nos templates (serão substituídas automaticamente):
- **{nome}** - Nome do cliente
- **{telefone}** - Telefone do cliente  
- **{vencimento}** - Data de vencimento
- **{valor}** - Valor mensal
- **{plano}** - Nome do plano/serviço

### Passo 4: Configurar Template
1. **Nome do template** (ex: "Cobrança Padrão")
2. **Tipo**: cobranca, renovacao, aviso
3. **Mensagem**: Digite o texto com as variáveis
4. **Ativo**: Sim/Não (se será usado automaticamente)

---

## 📤 4. ENVIANDO MENSAGENS MANUAIS

### Passo 1: Selecionar Cliente
1. Vá em **👥 Gestão de Clientes**
2. Clique em **📋 Listar Clientes**
3. Encontre o cliente desejado
4. Clique no botão **💬** ao lado do nome

### Passo 2: Escolher Template
1. Será mostrada lista de templates disponíveis
2. Clique no template que deseja usar
3. Ou escolha **✏️ Mensagem Personalizada**

### Passo 3: Revisar Mensagem
- O sistema mostrará preview da mensagem
- Variáveis já estarão substituídas pelos dados do cliente
- Confira se está tudo correto

### Passo 4: Enviar
- Clique em **📤 Enviar Agora**
- Aguarde confirmação de envio
- Mensagem será registrada no histórico

---

## ⏰ 5. CONFIGURANDO ENVIOS AUTOMÁTICOS

### Passo 1: Acessar Agendador
1. Vá em **⚙️ Configurações**
2. Clique em **⏰ Agendador**

### Passo 2: Configurar Horário
1. **Horário de verificação**: Que horas verificar vencimentos (ex: 09:00)
2. **Dias da semana**: Quais dias verificar
3. **Template padrão**: Qual template usar para cobranças

### Passo 3: Regras de Envio
**REGRA IMPORTANTE:** O sistema envia mensagens automáticas apenas:
- **1 dia após** o vencimento (não antes, não depois)
- Para clientes que **aceitam** receber mensagens automáticas
- **Uma vez por dia** no horário configurado

### Passo 4: Ativar Sistema
- Marque **"Envios automáticos ativos"**
- Clique em **💾 Salvar Configurações**

---

## 📊 6. GERENCIANDO CLIENTES

### Visualizar Lista de Clientes
**👥 Gestão de Clientes** → **📋 Listar Clientes**

**Informações mostradas:**
- Nome e data de vencimento
- Status: 🟢 Em dia / 🟡 Vence hoje / 🔴 Vencido
- Última mensagem enviada
- Botões de ação

### Buscar Cliente Específico
1. **👥 Gestão de Clientes** → **🔍 Buscar Cliente**
2. Digite parte do nome ou telefone
3. Sistema mostrará clientes encontrados

### Editar Dados do Cliente
1. Na lista, clique no **✏️** ao lado do cliente
2. Escolha que dados alterar:
   - Nome, telefone, vencimento
   - Valor, plano, observações
   - Preferências de mensagens

### Renovar Cliente
1. Na lista, clique no **🔄** ao lado do cliente
2. Escolha nova data de vencimento:
   - Manter mesma data (apenas quitar)
   - Definir nova data de vencimento
3. Cliente ficará em dia novamente

---

## 📈 7. RELATÓRIOS E ESTATÍSTICAS

### Relatório Rápido
**📊 Relatórios** → **📈 Relatório Rápido**
- Resumo de clientes por status
- Valores esperados vs recebidos
- Clientes vencendo nos próximos dias

### Relatório Detalhado
**📊 Relatórios** → **📋 Relatório Completo**
- Análise dos últimos 30 dias
- Histórico de mensagens enviadas
- Performance de cobrança
- Comparativo mensal

### Relatório por Período
1. **📊 Relatórios** → **📅 Por Período**
2. Escolha período: 7 dias, 30 dias, 3 meses, 6 meses
3. Visualize estatísticas específicas

---

## ⚙️ 8. CONFIGURAÇÕES GERAIS

### Dados da Empresa
**⚙️ Configurações** → **🏢 Empresa**
- Nome da empresa
- Chave PIX para recebimentos
- Telefone de contato
- Nome do titular

### Configurações de Sistema
**⚙️ Configurações** → **🔧 Sistema**
- Valor mensal padrão
- Dias de teste gratuito
- Fuso horário
- Configurações de backup

---

## ❓ 9. SOLUÇÃO DE PROBLEMAS

### WhatsApp Desconectado
**Problema:** Mensagens não estão sendo enviadas
**Solução:**
1. Vá em **📱 WhatsApp** 
2. Verifique status da conexão
3. Se desconectado, gere novo QR Code
4. Reconecte seguindo os passos do item 1

### Cliente Não Recebe Mensagens
**Possíveis causas:**
1. **Telefone incorreto** - Verifique se tem DDD e está correto
2. **WhatsApp desconectado** - Reconecte o WhatsApp
3. **Cliente bloqueou** - Telefone pode ter bloqueado mensagens
4. **Preferências** - Cliente pode ter desabilitado mensagens automáticas

### Mensagens Não Enviadas Automaticamente
**Verifique:**
1. **Agendador ativo** - Configurações → Agendador
2. **Template configurado** - Templates → Verificar se existe template de cobrança
3. **Horário correto** - Se já passou do horário configurado
4. **Cliente elegível** - Se venceu há exatamente 1 dia

### Erro ao Cadastrar Cliente
**Soluções:**
1. **Telefone** - Use apenas números, com DDD (11987654321)
2. **Data** - Use formato dd/mm/aaaa (01/12/2024)
3. **Valor** - Use ponto para decimais (50.00)

---

## 💡 10. DICAS E MELHORES PRÁTICAS

### Para Templates Eficazes
- ✅ Use linguagem amigável e profissional
- ✅ Inclua sempre as variáveis {nome} para personalizar
- ✅ Deixe claro valor e forma de pagamento
- ✅ Ofereça canal de contato para dúvidas
- ❌ Evite textos muito longos
- ❌ Não use linguagem agressiva

### Para Gestão de Clientes
- ✅ Mantenha dados sempre atualizados
- ✅ Configure observações importantes
- ✅ Use planos descritivos ("Premium", "Básico")
- ✅ Defina datas de vencimento estratégicas
- ✅ Monitore relatórios regularmente

### Para Envios Automáticos
- ✅ Configure horário comercial (9h às 17h)
- ✅ Teste templates antes de ativar automação
- ✅ Monitore histórico de envios
- ✅ Respeite clientes que não querem receber automático
- ✅ Mantenha WhatsApp sempre conectado

### Para Cobrança Eficiente
- ✅ Envie mensagem apenas 1 dia após vencimento
- ✅ Facilite formas de pagamento (PIX, etc)
- ✅ Seja claro sobre consequências do não pagamento
- ✅ Ofereça canais de negociação
- ✅ Mantenha histórico organizado

---

## 📞 11. SUPORTE

### Dentro do Sistema
- Use o botão **❓ Ajuda** no menu principal
- Acesse logs de erro em **⚙️ Configurações** → **📋 Logs**

### Contato Direto
- Para problemas técnicos críticos
- Erros de sistema ou bugs
- Dúvidas sobre funcionalidades avançadas

### Documentação
- Este guia está sempre disponível em **⚙️ Configurações** → **📚 Guia do Usuário**
- Mantenha este guia salvo para consultas rápidas

---

## ✅ RESUMO RÁPIDO

1. **Conecte WhatsApp** (📱 WhatsApp → Configurar)
2. **Crie templates** (⚙️ Configurações → Templates)
3. **Configure agendador** (⚙️ Configurações → Agendador)
4. **Cadastre clientes** (👥 Gestão → Cadastrar Cliente)
5. **Monitore vencimentos** (👥 Gestão → Listar Clientes)
6. **Acompanhe relatórios** (📊 Relatórios)

**🎯 Pronto! Seu sistema está configurado e funcionando!**

---

*📅 Última atualização: Agosto 2025*
*🔄 Este guia é atualizado automaticamente*
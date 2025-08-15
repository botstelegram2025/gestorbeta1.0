-- COMANDOS SQL PARA VERIFICAR TABELAS NO RAILWAY
-- Execute estes comandos no painel Railway Database Query

-- 1. LISTAR TODAS AS TABELAS
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- 2. CONTAR REGISTROS EM CADA TABELA
SELECT 
    'clientes' as tabela, COUNT(*) as registros FROM clientes
UNION ALL
SELECT 'templates', COUNT(*) FROM templates
UNION ALL
SELECT 'usuarios', COUNT(*) FROM usuarios
UNION ALL
SELECT 'configuracoes', COUNT(*) FROM configuracoes
UNION ALL
SELECT 'logs_envio', COUNT(*) FROM logs_envio
UNION ALL
SELECT 'fila_mensagens', COUNT(*) FROM fila_mensagens;

-- 3. VER ESTRUTURA DA TABELA CLIENTES
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'clientes'
ORDER BY ordinal_position;

-- 4. VER TEMPLATES PADRÃO INSERIDOS
SELECT id, nome, tipo, ativo 
FROM templates 
ORDER BY id;

-- 5. VER CONFIGURAÇÕES DO SISTEMA
SELECT chave, valor, descricao 
FROM configuracoes 
ORDER BY chave;

-- 6. TESTAR INSERÇÃO DE CLIENTE (EXEMPLO)
INSERT INTO clientes (
    chat_id_usuario, nome, telefone, pacote, valor, servidor, vencimento
) VALUES (
    123456789, 'Cliente Teste', '11999999999', 'Plano Básico', 29.90, 'Servidor 1', '2025-09-14'
);

-- 7. VERIFICAR SE CLIENTE FOI INSERIDO
SELECT * FROM clientes WHERE nome = 'Cliente Teste';

-- 8. VER TODOS OS SCHEMAS DISPONÍVEIS
SELECT schema_name FROM information_schema.schemata;

-- 9. VER INDICES CRIADOS
SELECT indexname, tablename, indexdef 
FROM pg_indexes 
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
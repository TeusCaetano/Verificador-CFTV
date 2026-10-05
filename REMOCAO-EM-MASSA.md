# Remoção em massa

Em Dispositivos, selecione câmeras pelas caixas de seleção.
A caixa do cabeçalho seleciona a página atual (até 50 linhas).
Selecionar todas do filtro inclui as outras páginas do filtro atual.
Ao alterar filtros, itens fora do filtro saem da seleção.
Clique em Remover selecionadas e confirme a quantidade e os nomes.
A exclusão usa as mesmas regras da remoção individual e exige administrador.
Remove cadastro e credenciais, registra auditoria e invalida o vídeo.
A operação é sequencial; falhas não desfazem as exclusões já concluídas.
O resultado informa removidas e pendências. Falhas permanecem selecionadas
quando ainda fazem parte do filtro. Evite fechar a página durante a remoção.

Atualize na pasta original preservando .env e execute:
docker compose up -d --build
Atualize o navegador com Ctrl+F5.
O pacote inclui a migração de setores globais já entregue. Caso ainda não a tenha
instalado, siga o backup descrito em SETORES-GLOBAIS.md antes de atualizar.

Validação simulada: cancelamento não exclui; somente selecionadas são enviadas;
falhas parciais preservam o cadastro/seleção; vídeo removido é fechado; resultado
é informado. Sintaxe JavaScript e IDs HTML verificados.

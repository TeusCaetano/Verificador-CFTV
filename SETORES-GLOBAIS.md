# Setores globais

Em Unidades e setores, cadastre o setor uma vez no catálogo global.
Cadastre a unidade e use Vincular setor existente para selecionar quais setores
ela possui. Repita o vínculo para outras unidades, reutilizando o mesmo setor.
Nos dispositivos e no mapa, só aparecem os setores vinculados à unidade.
Desvincular remove apenas o vínculo; excluir setor global exige nenhum vínculo
ou dispositivo associado. Operações de alteração exigem administrador.

A migração automática é transacional e pode ser repetida: unifica nomes iguais
ignorando maiúsculas e espaços nas extremidades; preserva vínculos das unidades
anteriores e atualiza os IDs nas câmeras. Grafias diferentes continuam separadas.
Como há migração do cadastro, faça um backup antes de atualizar.
Na pasta original da instalação execute:

docker compose exec -T db pg_dump -U scheffer -d scheffer > backup-antes-setores.sql

Copie os arquivos novos para a pasta original, preservando .env, e execute:
docker compose up -d --build
Depois Ctrl+F5.
Não use versões antigas do pacote após a migração sem restaurar o backup.

Validação: testes de migração idempotente, unificação de nomes, preservação de
vínculos de câmeras, reutilização por unidades, bloqueios de exclusão/desvínculo,
e regressão do posicionamento. Interface ainda exige conferência na instalação.

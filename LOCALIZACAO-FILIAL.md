# Corrigir localização da filial

Abra Unidades e setores → Editar localização na filial. Informe latitude e longitude corretas e escolha o alcance.

- Somente câmeras no centro antigo: preserva as posições individuais já distribuídas (tolerância de 0,000001 grau).
- Apenas centro: não altera câmeras existentes; novos cadastros usam o centro corrigido.
- Todas: redefine todas as câmeras vinculadas, inclusive canais livres, no novo ponto.

A tela mostra a quantidade e pede confirmação. Alteração atômica, somente administrador, com auditoria. Não muda conexão, credenciais, setor nem estado de monitoramento. Após salvar, selecione a filial no mapa e clique Centralizar.

Instalação: faça backup, copie o conteúdo desta pasta sobre a pasta original mantendo .env e execute docker compose up -d --build. Atualize o navegador com Ctrl+F5.

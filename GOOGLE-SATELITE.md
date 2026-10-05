# Google Satélite a partir do zoom 17

O sistema abre no dashboard e usa Ruas como mapa padrão em cada nova sessão. No mapa, o modo «Google a partir do zoom 17» vem ativado.
Esri é usado até o nível 16. A partir do nível 17, carrega a API oficial Google Maps e
reaproveita a mesma instância durante a sessão. Ao reduzir para 16 ou menos, retorna ao Esri. No modo Ruas, nenhum nível de zoom ativa Google. Selecione Satélite Esri para
ativar a troca automática a partir do zoom 17.
A seleção manual «Google Satélite» continua disponível; desmarque o modo automático
para permanecer no Google em qualquer zoom. Imagens Google dependem de cobertura,
internet, chave válida e faturamento ativo; a nitidez não é garantida em toda área.

## Ativação
1. No Google Cloud, ative Maps JavaScript API e vincule uma conta de faturamento.
2. Crie uma chave com restrição de API somente para Maps JavaScript API.
3. Restrinja os sites autorizados aos endereços usados na instalação, por exemplo
   http://localhost:8083/* e http://127.0.0.1:8083/*.
4. No .env da instalação existente, adicione uma linha:
   GOOGLE_MAPS_API_KEY=SUA_CHAVE_AQUI
5. Execute configurar.ps1 e docker compose up -d --build. Atualize com Ctrl+F5.
A chave de mapas é pública no navegador por definição; restrições são necessárias.
Não altere DB_PASSWORD, CAMERA_KEY ou ADMIN_PASSWORD.

## Atualização Windows
Copie o conteúdo deste pacote para a pasta original da instalação:
C:\Users\jose.santos\Downloads\scheffer-etapa-3\scheffer-etapa-3
Preserve o .env existente e o banco. Não execute docker compose down -v.

## Controle de uso
Configure cotas na console Google Cloud. O sistema não cria nem aplica cotas Google.
Uma nova sessão/página pode produzir novo carregamento. Atualizações dos marcadores
reutilizam o mapa existente. Quando uma chave falta ou o carregamento falha, o Esri
permanece disponível. Erros de autorização Google também aparecem na tela.

## Validação
Sintaxe JavaScript/Python verificada. Teste simulado verificou que a API não carrega
antes do nível 17 e que a instância é reutilizada. Validação real de imagem,
faturamento e chave depende da configuração do projeto Google na instalação.

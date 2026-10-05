# Conversão automática sob demanda

H.264 segue direto, sem recodificação. H.265/HEVC é identificado pelo monitor (cache até 180s) ou por consulta do codec ao abrir o vídeo. A prévia convertida usa H.264, até 1280x720 sem ampliar imagens menores, 15fps, limite de bitrate de 1,5Mbps, áudio AAC quando presente e duas threads para decodificação/codificação. Não altera o codec configurado no gravador nem grava vídeos.

Limite padrão: duas câmeras H.265 distintas simultâneas. Mesma câmera compartilha processo entre operadores. TRANSCODE_MAX no .env permite 1 a 4; mantenha 2 no piloto. Câmeras H.264 não usam vagas. Sem vagas, a abertura informa o limite; não afeta monitoramento.

Conversor encerra após 45s sem requisições do player (limpeza a cada 5s), ao editar/remover ou desligar app. Processos encerrados podem ser reiniciados pelo botão reproduzir. Conversões não são iniciadas para todo o parque. RTSP de publicação é interno ao Docker, sem porta publicada no Windows. Credenciais não são enviadas ao navegador nem aos logs do FFmpeg.

## Atualização
Copie conteúdo desta pasta sobre a pasta original preservando .env.
Execute:
    docker compose up -d --build
    docker compose restart video
Depois Ctrl+F5. O restart video é necessário para ativar a recepção RTSP interna no arquivo mediamtx.yml.

## Validação
Teste uma câmera H.264 e uma H.265, feche a H.265 e confira CPU após cerca de 50s. Duas câmeras H.265 podem ser abertas; uma terceira deve informar limite. Testes automatizados cobrem seleção de codec, compartilhamento, limite, encerramento e escopo da localização. FFmpeg converteu uma amostra HEVC para H.264 a 15fps. Reprodução com NVR real e desempenho precisam ser confirmados no Windows. O primeiro acesso sem codec em cache pode demorar para identificar o stream. HLS ainda tem atraso de transmissão; conversão não elimina latência da VPN nem garante imagem útil da câmera.

Diagnóstico: docker compose logs --tail=100 video app.

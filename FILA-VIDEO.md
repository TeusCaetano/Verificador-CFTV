# Abertura e troca de canais

Cada aba tem identificador de reprodução. Abrir nova câmera cancela a preparação anterior da mesma aba no servidor. FFprobe cancelável verifica o codec em até 18s; cancelamento mata subprocesso e libera vaga. Clientes/operadores diferentes não são cancelados. Mantém teto de duas preparações simultâneas e espera de até 4s por vaga.

Ao fechar, o navegador solicita liberação de tickets da aba. Conversor é encerrado se não houver outro ticket recente de operador ativo para a câmera. Encerramento em ociosidade permanece como proteção adicional. Rede/HLS/gravador ainda podem impor demora; o ajuste não garante abertura instantânea.

Bolinha da janela fica verde quando o navegador recebe avanço do vídeo; título acessível informa “Vídeo recebido agora” e resultado do monitor separadamente. Após 5s sem avanço, volta ao estado do monitor. Não modifica estado histórico, alertas ou totais do dashboard com base apenas no player. Receber vídeo não garante conteúdo útil da câmera física.

Atualização: copie conteúdo sobre pasta original preservando .env; docker compose up -d --build; Ctrl+F5. Teste troca rápida de canais e fechamento; confira vídeo sem exigência de aguardar pedidos abandonados. Layout preservado.

Verificações: cancelamento mata subprocesso, identificação da última seleção por aba, isolamento entre abas, rotas H264/H265, fallback de estado NVD. Testes locais simulados; verificar gravação real no parque.

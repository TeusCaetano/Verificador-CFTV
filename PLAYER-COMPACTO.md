Janela de 390px, vídeo 16:9 e diagnóstico recolhido. Player aguarda playlist HLS válida, até 3 tentativas, cada requisição até 30s, sem alterar cadastro ou status de monitoramento. Uma recuperação de erro de mídia. Cancelamento ao fechar/trocar câmera impede abertura tardia.

Atualize a pasta original preservando .env, execute docker compose up -d --build e Ctrl+F5. Se o vídeo persistir indisponível, envie docker compose logs --tail=150 video app. A presença de stream RTSP não garante reprodução HLS.

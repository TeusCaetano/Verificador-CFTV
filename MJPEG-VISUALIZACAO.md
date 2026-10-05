# Visualização MJPEG — 05/10/2026

Corrige a mensagem `Codec não suportado para visualização: mjpeg`. O stream RTSP MJPEG passa pelo conversor FFmpeg existente e é publicado em H.264 para o player HLS. O layout e os cadastros não são alterados.

## Atualizar somente o aplicativo

1. Extraia o ZIP e copie o CONTEÚDO de `scheffer-etapa-3\backend` para a pasta original abaixo, substituindo os arquivos do programa:

   `C:\Users\jose.santos\Downloads\scheffer-etapa-3\scheffer-etapa-3\backend`

2. Preserve `.env`, o banco e os backups. No Prompt de Comando, execute:

```bat
cd /d C:\Users\jose.santos\Downloads\scheffer-etapa-3\scheffer-etapa-3
docker compose up -d --build --no-deps app
```

3. Abra http://127.0.0.1:8083, pressione Ctrl+F5 e faça login novamente se solicitado. Teste a câmera `UP_3LGS_NVD09-CAM03`, que apresentou MJPEG.

Não é necessário remover ou recadastrar dispositivos. O pacote não contém `.env`, banco, senhas ou backups.

## Comportamento

- H.264: mantém encaminhamento direto pelo gateway.
- H.265/HEVC e MJPEG: utiliza conversão sob demanda para H.264.
- Prévia mantém o perfil existente de até 640 × 360 pixels, preservando proporção, até 10 fps e bitrate máximo configurado de 600 kbit/s.
- Mantém mapeamento opcional de áudio, cancelamento, expiração e reutilização do conversor.
- TRANSCODE_MAX continua com padrão 2: este limite é compartilhado por vídeos H.265 e MJPEG, contando canais em conversão, não operadores.
- Fechar uma câmera permite liberar seu conversor conforme as regras existentes de sessões e expiração. Mensagens do limite agora mencionam qualquer câmera em conversão.

A conversão usa CPU. Se o gravador oferecer H.264 no stream selecionado, esse codec evita a conversão neste sistema. A compatibilidade depende de o stream RTSP ser recebido e decodificado; o teste não substitui a validação na VPN e no equipamento real.

## Validação

Teste de rotas para H.264, HEVC e MJPEG, com reutilização do processo. Teste FFmpeg real: cria dez quadros MJPEG de 800 × 600, aplica o mesmo decodificador, filtros de prévia e codificador H.264 do conversor, e verifica codec H.264, yuv420p e tamanho máximo de 640 × 360 no resultado. Neste teste, arquivos locais substituem o transporte RTSP; o gravador real não foi acessado.

O pacote conserva a integração Hikvision, as correções estruturais e o reparo da inicialização da interface.

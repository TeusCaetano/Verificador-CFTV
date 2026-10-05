# Atualização estrutural — 2 de outubro de 2026

## Instalação existente

Use o Prompt de Comando do Windows (CMD). Faça um backup antes da atualização:

```bat
cd /d C:\Users\jose.santos\Downloads\scheffer-etapa-3\scheffer-etapa-3
docker compose exec -T db pg_dump -U scheffer -d scheffer -Fc > backup-antes-correcao.dump
```

Extraia o ZIP e copie o CONTEÚDO da pasta `scheffer-etapa-3` para a pasta original acima, substituindo os arquivos do programa. Preserve o arquivo `.env` existente. O ZIP não inclui senhas nem o `.env`.

Execute na mesma pasta original:

```bat
docker compose up -d --build
```

Abra http://127.0.0.1:8083 e pressione Ctrl+F5. Não execute `docker compose down -v` e não inicie o projeto em outra pasta: isso pode selecionar outro volume de banco. Não é necessário gerar novamente a chave de câmeras.

## Alterações

- Monitor RTSP com consulta rápida: até 2 segundos para conexão TCP e até 6 segundos para ffprobe. Resultado inconclusivo segue para confirmação separada, sem registrar um falso offline.
- Até 16 verificações rápidas simultâneas, configuráveis por MONITOR_WORKERS, e 2 confirmações lentas. Limite padrão de 2 consultas por gravador; com esse padrão, uma confirmação lenta deixa uma vaga para canais saudáveis do mesmo gravador.
- Fila de confirmações por ordem de chegada, com intervalo contado após a conclusão. As tentativas completas continuam com limites de 18 e 40 segundos para streams lentos.
- Resultados de testes são descartados se IP, porta, canal, fabricante, credenciais, stream, caminho RTSP ou modo livre mudarem durante a verificação. PostgreSQL utiliza bloqueio de linha na atualização.
- Alterar nome, localização ou demais metadados sem mudar a conexão preserva o último status e os alertas. A atualização cria revisões para os cadastros existentes sem zerar suas verificações.
- Preparação do gateway e encerramento de FFmpeg não seguram o bloqueio compartilhado dos conversores. Cancelamento durante a preparação evita iniciar um processo abandonado.
- Liberação do vídeo anterior ocorre fora do processamento assíncrono principal da API.
- Proxy de vídeo reutiliza conexões HTTP ao gateway.
- Atualização periódica da interface passa de oito requisições para uma consulta unificada, com cache compartilhado de até três segundos. Escritas bem-sucedidas invalidam esse cache. A interface faz uma renderização geral por atualização.
- Mapa não é reconstruído quando está oculto; o mapa padrão evita reconstruir marcadores sem mudança. Câmeras na mesma coordenada são agrupadas antes das comparações espaciais, preservando os números e a expansão dos grupos.
- Verificações consecutivas com o mesmo resultado estendem um intervalo de cobertura, reduzindo novos registros no histórico. Lacunas e mudanças de estado continuam preservadas.
- Relatórios percorrem o histórico em lotes e compactam intervalos antes do cálculo. Removido o bloqueio de 200 mil observações; registros históricos existentes não são apagados.
- Índice composto por câmera, horário e ID é criado automaticamente. A varredura de alertas e a listagem de setores utilizam leituras em lote.

## Validação

34 testes Python em 15 arquivos: cadastro, credenciais, canais livres, setores, localização, alertas, conversão, cancelamento, fila e relatórios. Verificações de sintaxe Python e JavaScript. Teste de agrupamento com mil câmeras na mesma coordenada.

Novos testes reproduzem alteração de IP durante uma verificação, edição de metadados, atualização com cadastros anteriores, timeout rápido, remoção durante preparação, preservação das lacunas do histórico e três canais saudáveis enquanto um quarto canal do mesmo gravador aguarda confirmação lenta. A compactação também foi exercitada com 210.001 observações consecutivas.

## Validação no parque real

Os testes usaram SQLite e respostas simuladas, sem acesso à VPN, às câmeras ou ao Docker do computador de instalação. Ainda é necessário conferir CPU, memória, atraso das verificações e abertura de H.264/H.265 no piloto. Não há promessa de capacidade para mil câmeras baseada somente nesses testes.

Após instalar, observe por alguns minutos o contador de verificações recentes e teste canais conhecidos online e offline, incluindo o gravador final 5. Para diagnóstico, execute:

```bat
docker compose logs --tail=150 app video
docker stats --no-stream
```

A confirmação lenta continua limitada a dois canais por vez; muitos canais inconclusivos podem formar fila. Um stream RTSP disponível ainda não comprova que a câmera física transmite imagem útil. A conversão continua limitada por TRANSCODE_MAX (padrão 2). Monitoramento e conversão ainda compartilham o serviço app; não aumente o número de processos da API, pois sessões e tickets permanecem em memória. Não foi feita exclusão automática do histórico, separação em serviços ou troca de protocolos.

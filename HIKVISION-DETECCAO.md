# Detecção de canais Intelbras e Hikvision — 05/10/2026

## Atualização da instalação existente

O pacote contém o sistema completo, incluindo o reparo da inicialização da interface. Não contém `.env`, senhas, banco de dados ou backup. Preserve a pasta original e o arquivo `.env`.

1. Faça uma nova cópia do banco no Prompt de Comando (CMD):

```bat
cd /d C:\Users\jose.santos\Downloads\scheffer-etapa-3\scheffer-etapa-3
docker exec scheffer-etapa-3-db-1 pg_dump -U scheffer -d scheffer -Fc > backup-antes-hikvision.dump
```

2. Extraia o ZIP. Copie o conteúdo das pastas `backend` e `frontend` extraídas para as mesmas pastas na instalação original, substituindo os arquivos do programa. Preserve `.env` e os backups.
3. No mesmo Prompt e na mesma pasta original, execute:

```bat
docker compose up -d --build --no-deps app
```

4. Abra http://127.0.0.1:8083 e pressione Ctrl+F5. Faça login novamente se necessário.

Não é necessário reconfigurar senhas, gerar outra chave de câmeras, restaurar banco ou recadastrar os 240 dispositivos. Esta alteração não faz migração de banco nem modifica gravadores: a detecção executa somente GET, e o cadastro continua exigindo revisão e salvamento pelo operador.

## Como testar

Em Cadastrar gravador, selecione Hikvision. Informe IP, usuário, senha, canais e a porta RTSP como antes. Na seção de detecção, informe a porta WEB HTTP/HTTPS do gravador e clique em Detectar canais. Não use a porta RTSP ou SDK 8000 no campo porta web. Para modelos que ofereçam a opção, habilite o serviço ISAPI nas configurações do gravador. A porta web precisa estar acessível pela VPN, e o usuário precisa ter permissão para consultar as câmeras.

- Câmera cadastrada: canal ocupado; falha de comunicação não o transforma em canal livre.
- Canal livre: origem de câmera explicitamente vazia ou desabilitada sem endereço de câmera no cadastro.
- Revisão manual: canal omitido, resposta incompleta, firmware sem suporte, permissão insuficiente, numeração desconhecida, configuração contraditória ou timeout.

Os canais confirmados como livres são marcados na prévia. Revise os inconclusivos e confirme a revisão manual antes de validar. Depois confira a prévia e salve o lote.

A integração consulta `/ISAPI/ContentMgmt/InputProxy/channels`, usando IDs conforme retornados pelo gravador. Não converte automaticamente IDs 33, 34 etc. para canais 1, 2. Não usa IDs de stream como 101/102 para determinar ocupação. Gravadores híbridos podem exigir conferência manual dos canais analógicos.

Câmeras sem instalação física em um canal cujo endereço já esteja configurado não podem ser distinguidas de câmeras configuradas mas temporariamente desconectadas somente pelo cadastro. Esses canais permanecem ocupados para não desativar monitoramento indevidamente.

## Compatibilidade e validação

Integração Hikvision ISAPI para inventário de entradas digitais. O suporte depende do modelo, firmware, permissões e acessibilidade da porta web. O monitoramento Hikvision por RTSP e os caminhos de vídeo existentes foram mantidos. A consulta opcional de estado do gravador Intelbras continua separada desta função.

Testes incluem XML com namespaces, origem IPv4/IPv6/hostname, canal livre, câmera offline, IDs de NVR, numeração de híbridos, XML inválido/duplicado, autenticação Digest/Basic, acesso negado e timeout. Não houve acesso aos gravadores reais pela VPN; valide primeiro em um equipamento Hikvision antes de importar muitos canais.

Referências técnicas: documentação Hikvision ISAPI e SDK em https://open.hikvision.com/ e lista oficial de portas em https://pro-av.hikvision.com/content/dam/hikvision/ca/bulletin/technical-bulletin/technical-article/tb_network_port_list.pdf .

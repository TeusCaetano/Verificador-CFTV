# Reparo da interface — 02/10/2026

O erro `Cannot access 'lastMapSignature' before initialization` interrompia o primeiro desenho do mapa antes da instalação dos eventos de login e da consulta aos cadastros. A declaração foi movida para antes da primeira renderização. O HTML também recebe uma nova URL para o JavaScript, evitando reutilização da versão anterior em cache.

O usuário confirmou 240 registros no PostgreSQL e 240 registros acessíveis pelo aplicativo. O arquivo `backup-240-cameras.dump` foi criado com 316.963 bytes. A restauração do backup não foi necessária para este reparo; não foi validada uma restauração desse arquivo.

## Aplicar somente o reparo da interface

1. Extraia o ZIP atualizado.
2. Copie os arquivos da pasta `scheffer-etapa-3\frontend` extraída para a pasta existente abaixo, substituindo os arquivos da interface:

   `C:\Users\jose.santos\Downloads\scheffer-etapa-3\scheffer-etapa-3\frontend`

3. No Prompt de Comando, execute:

```bat
cd /d C:\Users\jose.santos\Downloads\scheffer-etapa-3\scheffer-etapa-3
docker compose up -d --build --no-deps app
```

4. Abra http://127.0.0.1:8083, pressione Ctrl+F5 e faça login novamente. Confira os 240 cadastros em Dispositivos e no Dashboard.

Este procedimento recria somente o aplicativo. Preserve `.env`, `backup-240-cameras.dump`, o banco e o volume existente. Não execute configurar.ps1, comandos de restauração ou remoção de volumes para corrigir a interface.

## Testes

O teste `tests/test_frontend_startup.js` executa os scripts da interface em um ambiente DOM e mapa simulados. Ele reproduz o erro com a antiga ordem das declarações, verifica abertura do login e consulta/carregamento de 240 câmeras simuladas após a correção. Inclui o script de integração do Google. Não é um teste conectado ao parque real.

```text
node tests/test_frontend_startup.js
```

O pacote continua contendo as correções estruturais anteriores e não inclui `.env`, senhas ou banco de dados.

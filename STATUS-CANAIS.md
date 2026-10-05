# Estado real dos canais Intelbras

Abra Dispositivos → Editar em um canal já salvo → Monitorar estado dos canais do NVD. Marque consultar estado, informe porta WEB e HTTP/HTTPS e salve. Para o NVD05 use a porta em que você acessa a interface web (4005 se esse é o endereço utilizado); não informe a RTSP 5005. A configuração vale para IP/porta RTSP/unidade de todos os canais desse gravador. Reutiliza credenciais de cada canal, já criptografadas.

API oficial Intelbras getCameraState via POST uniqueChannels [-1]. Numeração recebida zero-based é convertida para canais 1-based. Connected → online; Unconnect/Disable/UnInited/Empty/Hibernation → offline; Connecting/outros/missing → não verificada. Canal livre permanece opção de cadastro, nunca inferida de falha. Online nessa modalidade significa câmera conectada ao NVD; imagem útil não é validada.

Consulta compartilhada por gravador/credenciais por até 30s, prazo HTTP de 8s; outros NVDs não bloqueados por esse NVD. Firmware incompatível, autenticação rejeitada ou porta inacessível produz não verificada com diagnóstico; desativar opção retoma RTSP.

Último offline conhecido permanece offline se a verificação vence, acompanhado de “verificação vencida”. Não fabrica resultado novo, observação nem disponibilidade histórica: cobertura continua respeitando validade. Online vencido continua não verificada, last_status/checked_at preservados. Alertas de falta de verificação continuam possíveis; respostas inconclusivas não contam como falhas offline. Consulta direta alimenta o histórico e a confirmação de offline após 3 ciclos.

Atualize pasta original preservando .env e banco: docker compose up -d --build; Ctrl+F5. Nova tabela de configurações é criada automaticamente. Sem remoção ou recadastro.

Teste no NVD05: configurar porta web, aguardar próximo ciclo e conferir 27,28,29,31. Testes locais cobrem mapeamento 0→1, offline confirmado sem teste RTSP e offline vencido; firmware real depende de teste na instalação.

Documentação: https://botminio.apps.intelbras.com.br/dvr/HTTP_API_V3_59_Intelbras.pdf seção 4.6.29.

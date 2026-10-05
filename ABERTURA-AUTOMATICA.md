Abertura automática aguarda até 90s incluindo consulta inicial do codec. Reconsulta vídeo a cada 2s, requisições limitadas, até duas renovações do ticket após três falhas transitórias. Ao fechar/trocar cancela requisição pendente e não abre vídeo atrasado. Erros de sessão, cadastro, permissão e limite de conversão não geram tentativas indefinidas. Mantém layout aprovado e conversão leve.
Atualize pasta original preservando .env, docker compose up -d --build, Ctrl+F5.
Testes simulados: disponibilidade tardia, renovação, erro de autenticação e cancelamento. Validar com gravador real.

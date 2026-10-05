# Monitoramento com concorrência por gravador

A versão anterior limitava a 2 verificações para todo o parque. Agora há até
8 verificações simultâneas e no máximo 2 por gravador (mesmo IP/porta RTSP).
Uma fila considera prazos e idade da última verificação; canais de um gravador
com vagas ocupadas não impedem consultas aos outros gravadores.
Com 3 gravadores, o máximo simultâneo é 6; 8 é o limite global, não uma meta.
Os testes manuais contam com duas vagas extras; falhas de capacidade do monitor
são reagendadas em 2 segundos, em vez de adiar o canal por um minuto.
Canais livres continuam excluídos do monitoramento.

A validade dos resultados continua em 180s (ou 3 intervalos). Não mantém online
com resultado vencido e não altera disponibilidade histórica já registrada.
O resumo do mapa mostra verificações em andamento/capacidade e cadastros sem
verificação recente. Uma câmera que nunca foi verificada também entra nesse total.
Para falhas reais, as regras de alerta seguem as existentes.

Atualização na pasta original preservando .env:
docker compose up -d --build
Depois Ctrl+F5. Aguarde alguns minutos e acompanhe Não verificada e alertas.
Se continuarem altos, consulte docker compose logs --tail=80 app e o diagnóstico
do teste de um canal. Pode haver lentidão real, indisponibilidade ou falta de
capacidade. A melhoria não garante cobertura contínua para 1.000 câmeras sem
validar o tempo de resposta, capacidade dos gravadores e conexão VPN.

Cobertura histórica baixa pode incluir horas anteriores ao início do sistema
ou cadastro. Não é só um retrato da fila atual; não será artificialmente corrigida.

Testes: limites global/por gravador, gravador lento não bloqueando outro, prioridade
por idade, fila sem tarefas excedentes, simulação de 96 canais em 3 gravadores com
probes de 3s; quatro testes de nova tentativa de RTSP. Nove testes passaram.
Validação de carga no parque real continua necessária.

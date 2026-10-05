ATUALIZACAO: consulte HIKVISION-DETECCAO.md. O pacote atual inclui deteccao Hikvision via ISAPI, alem de Intelbras. Os detalhes abaixo registram a implementacao anterior.

# Detectar canais livres no cadastro do gravador

Disponível no formulário Canais do gravador, para Intelbras compatíveis com
GET /cgi-bin/LogicDeviceManager.cgi?action=getCameraAll.
Consulta somente leitura, com autenticação Digest e fallback Basic. Não altera
configuração no gravador e não consulta RTSP para inferir ausência de câmera.
Compatibilidade depende do firmware. Hikvision permanece com revisão manual.

Para o NVD 7132 final 5:
- IP: 10.104.3.5
- Porta web: 4005 (conforme sua tela do gravador)
- Protocolo de gerenciamento: HTTP
- Canais: 1-32
- Porta RTSP: informe a porta RTSP real; não confunda com a porta web.
- Usuário/senha: credenciais do gravador com permissão de consulta.

Preencha os dados e clique Detectar canais ou Validar canais. A consulta automática
vem ativada. Confira a tabela de resultados e as caixas Canal livre antes de
Validar canais → Salvar lote. Canal 32 será marcado livre somente se a lista
completa reconhecida confirmar ausência dele. Câmera com endereço cadastrado,
mesmo offline, continua cadastrada e será monitorada normalmente.

Erro de autenticação, porta, VPN, formato ou numeração não reconhecida resulta
em revisão manual; não marca canal livre por falha de vídeo. Canais inconclusivos
exigem que você revise as caixas e confirme a revisão. É possível desativar a
consulta automática e manter o cadastro manual. A detecção não altera cadastros
já salvos. Confirme numeração e ocupação pela tela do NVR na primeira utilização.

Atualização: copie o conteúdo para a pasta original preservando .env e execute:
docker compose up -d --build
Depois Ctrl+F5. Todos os ajustes anteriores estão incluídos.

Testes simulados: 31 câmeras e ausência do canal 32; offline com cadastro;
respostas vazias reconhecidas; formatos inválidos; número remoto diferente do
canal NVR; HTTP 401/403/404; página de login; sucesso sem expor senha.
Cinco testes Python passaram. Sintaxe e estrutura HTML verificadas.
A validação com o seu equipamento físico ainda é necessária.

Referência: HTTP API V3.59 Intelbras, seção 4.6.25.
https://botminio.apps.intelbras.com.br/dvr/HTTP_API_V3_59_Intelbras.pdf

## Correção validada com a resposta do NVD 7132
Aceita campos de listas internas como DeviceInfo.VideoInputs[0].Enable.
Quando Enable e DeviceInfo.Enable são ambos false, o canal é livre mesmo
se o equipamento preservar endereço/identificador antigo. Canais habilitados
com câmera cadastrada permanecem monitorados, inclusive offline.
Resposta real fornecida: canais 1–31 cadastrados e 32 livre; canal Compose
interno fora do intervalo não interfere. Seis testes passaram.
O arquivo enviado e seus dados de acesso não estão incluídos no pacote.

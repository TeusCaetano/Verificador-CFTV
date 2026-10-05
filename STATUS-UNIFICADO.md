# Status unificado e consulta do gravador

A reprodução confirmada pelo navegador, com fragmentos recentes de vídeo recebidos pelo servidor, atualiza o estado do canal no cadastro e no painel. Apenas abrir a janela, obter uma playlist ou detectar o codec não confirma reprodução. Um resultado antigo de teste RTSP não substitui uma reprodução confirmada durante o teste. Alterações de conexão invalidam confirmações da configuração anterior.

O player exibe o mesmo estado do inventário. Vídeo disponível não comprova imagem útil da câmera física: gravadores podem fornecer uma tela de câmera desconectada.

## Estado direto do Intelbras

Abra Editar em um canal salvo, clique em Estado dos canais no gravador, habilite a consulta e informe a porta web HTTP/HTTPS do NVD e o protocolo. Não use a porta RTSP neste campo. A configuração é compartilhada pelos canais deste gravador. A consulta depende da compatibilidade do firmware e das permissões do usuário. Se a consulta falhar, o monitor usa RTSP e registra essa informação no diagnóstico. Um estado desconectado informado pelo gravador tem prioridade sobre a reprodução.

No Hikvision, esta versão detecta os canais cadastrados por ISAPI; a consulta direta de estado físico dos canais ainda não está implementada.

## Atualizar a instalação existente

1. Faça uma cópia do arquivo .env e mantenha seu backup do banco.
2. Extraia este ZIP em uma pasta separada.
3. Copie as pastas backend e frontend para a pasta original do sistema, substituindo os arquivos correspondentes. Preserve o .env e use a pasta original scheffer-etapa-3\scheffer-etapa-3.
4. Execute nessa pasta:

```bat
docker compose up -d --build --no-deps app
```

5. Atualize o navegador com Ctrl+F5.

Não é necessário recriar o banco nem executar configurar.ps1. Os testes automatizados verificam a integração e usam respostas simuladas do gateway; a validação nos seus gravadores será feita no ambiente instalado.

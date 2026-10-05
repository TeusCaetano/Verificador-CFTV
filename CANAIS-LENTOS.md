# Tolerância a inicialização lenta de streams

O teste manual e o monitor automático usam uma segunda tentativa de até 40s
apenas após timeout, resposta sem streams ou mensagem de timeout reconhecida.
A primeira tentativa mantém o limite de 18s. Autenticação rejeitada e caminhos
inválidos não geram tentativas adicionais. Não muda o stream cadastrado.
Canais normais são verificados uma vez; canais lentos podem ocupar um trabalhador
por até cerca de 58s. O histórico registra somente o resultado final do teste.
Não transforma câmera offline em canal livre.

Atualize na pasta original preservando .env:
docker compose up -d --build
Depois Ctrl+F5. Abra Editar no UP_3LGS_NVD07-CAM03 e Testar cadastro salvo.
Se retornar online após nova tentativa, a demora foi contornada. Se persistir,
confira o stream principal/secundário. Uma câmera pode ter o principal funcional
e o secundário desativado; o teste do cadastro usa exatamente o stream escolhido.
Envie o diagnóstico exibido, sem credenciais, para investigação adicional.

Quatro testes simulados: timeout seguido de sucesso; sucesso na primeira;
autenticação sem repetição; duas tentativas limitadas com diagnóstico sem senha.
A conexão real com o NVR ainda precisa ser verificada na instalação.

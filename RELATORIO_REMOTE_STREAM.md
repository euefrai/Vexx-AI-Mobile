# Transmissão e controle remoto — 28/10/2026

## Implementado
- Atualização encadeada, com uma captura em andamento por conexão. Intervalo mínimo de 250 ms entre inícios (~4 quadros/s quando a rede permite), substituindo polling fixo de 1600 ms.
- JPEG adaptativo: até 1920 px/qualidade 78; 1280 px quando a média de resposta supera 650 ms; 960 px/62 acima de 1400 ms. Média inclui resposta e decodificação. Limites do agente/relay: 1920 px/85.
- Decodifica a próxima imagem antes de substituir a atual. Respostas antigas são descartadas após desconexão/reconexão ou troca de conta.
- Até duas tentativas adicionais de captura com espera progressiva; falhas de autenticação encerram imediatamente. Comandos de entrada nunca são repetidos automaticamente.
- Espera mínima entre entradas reduzida de 550 para 100 ms. Fila continua limitada a 24 comandos; movimentos/rolagem consecutivos são agrupados. Limites por usuário e globais continuam ativos e configuráveis.
- Toque simples, duplo toque, pressão longa para botão direito, arrasto e rolagem vertical/horizontal com dois dedos. Roda do mouse também é aceita.
- Arrasto enviado ao soltar como um comando com 2–32 pontos; execução limitada a cerca de 248 ms de pausas. O botão é liberado em finally inclusive quando o movimento falha. Nenhum botão fica pressionado aguardando uma segunda requisição de rede.
- Mantidas autorização por conta, confirmação no Windows, CSRF, revogação e bloqueio de controle durante confirmação. Service worker atualizado.

## Arquivos
public/remote.js, public/sw.js, remoto.py, server.py, tests/test_remote_stream.py e tools/test_remote_stream.cjs.

## Verificação
- 29 testes preexistentes de remoto/permissões passaram após as mudanças iniciais; incluem captura JPEG real no Windows.
- Harness determinístico Node executou arrasto, duplo toque sem clique duplicado, dois dedos, cancelamento, exclusão de captura simultânea e descarte de frame antigo.
- Novos testes negativos validam pontos inválidos/NaN/excesso, liberação após falha nativa e rolagem horizontal. Eventos nativos de entrada simulados; nenhum clique real no computador do usuário.
- Suíte completa: 1.903 passed, 4 skipped, 2 warnings em 163,25 s; exit 0. Log: qa-artifacts/remote-stream-full.log. Avisos existentes de mss e TestClient. node --check e git diff --check também passaram.

## Limitações e publicação
O transporte continua sendo JPEG por HTTP através do relay existente, não vídeo WebRTC. Quatro quadros/s é teto configurado, não FPS nem latência medidos em produção. Não há teste em celular físico, comparação WAN, teste visual em navegador ou validação de arrasto em aplicativos reais nesta entrega. Pinça/zoom local e atalhos com modificadores não foram adicionados. Arrasto não acompanha o dedo no PC em tempo real: ocorre ao soltar.

A imagem maior pode consumir mais banda; a adaptação contém esse custo quando as respostas ficam lentas. Falhas transitórias não deixam pedidos ilimitados, mas dependem dos timeouts já existentes no relay. Variáveis de ambiente de limites de requisição podem manter limites antigos se configuradas explicitamente.

Mudanças locais. Para disponibilizá-las, será necessário publicar frontend/relay e atualizar o PC Agent para a mesma versão. Nenhum push, deploy ou reinício foi executado nesta etapa.

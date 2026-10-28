# Transmissão, rolagem e teclado remoto — 28/10/2026

## Implementado

- `/api/remote/frame` retorna JPEG binário, com dimensões, cursor e estado de controle nos cabeçalhos. Reutiliza os mesmos controles de sessão, CSRF, origem, revogação e grant de `/api/screen`. Sem armazenamento de capturas no relay; respostas `no-store, private`.
- O navegador usa Blob/Object URL, decodifica antes de trocar a imagem e libera as URLs antigas, canceladas e de conexões encerradas. A CSP permite `blob:` somente em imagens; scripts continuam restritos à própria origem. Relay antigo sem endpoint binário usa o transporte anterior.
- Cadência mínima de 125 ms (teto próximo de 8 quadros/s quando o caminho permite), mantendo uma requisição em andamento. Resolução/qualidade adaptam entre 960/62, 1280/72 e 1920/78. Timeout local de dez segundos; erros transitórios têm espera limitada e 429 respeita `Retry-After`.
- Captura/codificação saíram do loop que recebe comandos do agente: pool próprio de um worker, nenhuma fila de capturas acumuladas, conexão SQLite própria somente para leitura e verificação de grant antes de capturar e antes de enviar. O runtime contabiliza esse pool no encerramento seguro.
- Removida uma cópia RGB redundante na captura. Preservado o JPEG nativo, sem ampliar limites de imagem ou executar código recebido do cliente/modelo.
- Entradas consecutivas podem ser enviadas em lotes ordenados de até 12 comandos/400 caracteres. O agente valida o lote inteiro antes de executá-lo e cobra cada comando no limite nativo. Arrastos e lotes recursivos são recusados nesse caminho. Não se repetem comandos após timeout/falha de confirmação; apenas 404/405 sem execução e 429 anterior à execução permitem fallback/espera.
- Compatibilidade: lotes e rolagem precisa dependem das capacidades declaradas pelo agente; existe fallback para comandos simples. Limites continuam finitos: 24 itens na fila do celular e limites por usuário/globais no relay.
- Dois dedos agora acumulam todos os deslocamentos, inclusive movimentos pequenos e o último movimento antes de levantar o dedo. O agente aceita unidades menores de roda do Windows; rolagem horizontal também é preservada. Agentes antigos mantêm o modo de rolagem anterior.
- Teclado visível ao tocar em Teclado, com estado acessível e suporte a composição, acentos/emoji, colagem dividida sem cortar pares Unicode, apagar via `beforeinput` móvel, Enter/Tab/Esc/Delete e setas físicas. O campo não é salvo. Sob excesso de fila, o restante permanece no campo em vez de ser descartado.
- Quebras de linha e tabulações enviadas como texto viram Enter/Tab nativos. Mantidos consentimento Windows e bloqueio de entrada durante confirmação.

## Medições executadas

Artefato: `qa-artifacts/remote-latency-measurement.json`.

Captura real do Windows, pixels não salvos, 1280 px/qualidade 72, quatro amostras por variante após aquecimento:

| Medida local | Resultado |
| --- | --- |
| Mediana da captura na base `279e674` | 61,69 ms |
| Mediana atual | 54,22 ms |
| Corpo JSON/base64 do mesmo quadro | 129.507 bytes |
| Corpo JPEG binário | 97.024 bytes |
| Redução do corpo enviado ao celular | 25,08% |

Esta comparação é pontual e local; não mede latência de internet nem garante o mesmo ganho em outra tela/PC. O caminho agente → relay ainda usa o protocolo existente com base64. O ganho binário é no trecho relay → celular.

Chrome real, perfil temporário próprio, emulação móvel 390×844, tela e comandos simulados, atraso de servidor de 40 ms: **18 quadros, 7,66 fps observados**. Decodificação JPEG, cursor, eventos nativos de toque com dois dedos, entrada pelo navegador com acento/emoji/quebra de linha e desconexão passaram. Política CSP real do servidor aplicada ao teste. Sem erros de página. Isso não é teste de celular físico nem WAN/Render.

Artefatos locais: `qa-artifacts/remote-latency-browser/result.json`, `mobile-component.png`. O screenshot é de um fixture de componente, não a interface completa de produção. O primeiro harness selecionou por engano o alvo de uma extensão interna do Chrome; corrigida a seleção para o alvo de página do perfil descartável e repetido com sucesso.

## Testes

- 45 testes preexistentes de remoto/runtime passaram após as mudanças iniciais.
- Novos testes de JPEG autenticado, isolamento de owner, CSRF/origem, limites de lote, ordem/custo nativos, captura sem fila, revogação durante captura e contabilização/restauração dos dois pools.
- Harness Node: transporte legado/binário, liberação de Blob, composição sem duplicação, colagem Unicode longa, lotes, apagar móvel, movimento curto/final de dois dedos e descarte de imagem antiga.
- Validação nativa de entrada usa mocks; não se executaram cliques/teclas no desktop do operador.
- Suíte antes do último ajuste de CSP: 1.946 passed, 4 skipped, 2 warnings.
- Suíte final: **1.946 passed, 4 skipped, 2 warnings**, 168,47 s, exit 0. Avisos existentes de mss e TestClient. Log: `qa-artifacts/remote-latency-full-final.log`.
- `node --check` em `remote.js`, `app.js`, `jdui.js`; compilação Python e `git diff --check`: aprovados.

## Publicação e operação

A correção anterior da pesquisa foi enviada para `main` no início deste trabalho: `279e674`. Publicação desta etapa e atualização do PC Agent: pendentes da verificação final.

## Limites

- O transporte permanece por capturas JPEG/RPC, sem vídeo WebRTC ou conexão direta entre aparelhos. O relay e a latência de internet ainda limitam os quadros por segundo.
- Arrastos continuam sendo comandos limitados executados ao soltar, com liberação do botão em `finally`; não foi implementado botão pressionado entre requisições nem arrasto contínuo ao vivo.
- Não houve teste em celular físico/IME real Android ou iOS, aplicação remota de terceiros, rede móvel ou múltiplos usuários simultâneos em produção.
- Autocorreção local permanece desativada; composição é enviada apenas quando concluída para evitar trocas indevidas de palavras no PC.
- A execução nativa de um lote pode ser parcial caso o Windows falhe no meio. O cliente não repete esse lote automaticamente; não há promessa de transação para eventos de mouse/teclado.
- Variáveis de ambiente com limites antigos podem reduzir a cadência. O cliente espera o prazo informado pelo servidor em vez de desconectar ou contornar esse limite.

Arquivos principais: `server.py`, `pc_agent.py`, `agent_runtime.py`, `remoto.py`, `remote_access.py`, `public/remote.js`, `public/app.js`, `public/index.html`, `public/interface.css`, `public/sw.js`; testes/harnesses em `tests/test_remote_latency.py`, `tools/test_remote_stream.cjs` e `tools/chrome_remote_latency.py`.

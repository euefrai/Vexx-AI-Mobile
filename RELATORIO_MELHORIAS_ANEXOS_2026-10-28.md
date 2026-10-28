# Anexos — cancelamento e isolamento de envios

Base publicada: `91361a3`. Alterações desta etapa são locais.

## Correções

- Botão **Cancelar envio** durante o upload, sem apagar o texto ou os anexos pendentes. A tentativa seguinte reutiliza documentos já confirmados, evitando upload duplicado em falhas parciais.
- AbortController vinculado ao envio. Sair da conta interrompe os uploads imediatamente; a limpeza do rascunho só ocorre quando o logout é confirmado. Sessão expirada, troca de conta e limpeza do armazenamento também invalidam os envios.
- Cada envio captura conta, época da autenticação e geração do armazenamento. Respostas atrasadas são descartadas antes de atualizar o cache ou salvar a mensagem. A mensagem recebe explicitamente seu proprietário original.
- Progresso e botão de anexar são calculados para a conversa ativa. Concluir um envio em segundo plano não oculta o upload nem rola outra conversa.
- Remoção de anexos desabilitada durante o envio já iniciado; cancelamento disponível na etapa de upload. Após a gravação da mensagem começar, o cancelamento deixa de ser oferecido.
- HTTP 401 do upload volta ao login e limpa os dados transitórios do envio.

## Evidências

Três falhas foram reproduzidas contra o JavaScript publicado em `91361a3`, usando o mesmo harness assíncrono com DOM de teste: resposta tardia após logout, resposta tardia após troca de conta e um upload em segundo plano ocultando o progresso de outra conversa. Registro: `vexx-v598-dev/qa-artifacts/attachment-lifecycle-before-confirmed.log`.

Validação da correção:

- **77 testes focados aprovados**, incluindo 7 cenários que executam as funções reais do composer no Node: logout, troca de conta, cancelamento/retry, falha parcial/retry, progresso em outra conversa, limpeza com resposta tardia e HTTP 401.
- Chrome real, stack local isolado e celular emulado em 390 px: botão de cancelar visível com área de toque de 44 px; cancelamento abortou o sinal, preservou um anexo e não criou mensagem. O transporte desse primeiro pedido foi retido pelo harness antes da transmissão, portanto isso **não** demonstra rollback do servidor.
- Retry com transporte real: **1 upload, 1 documento e 1 mensagem**, apesar de duplo envio. Nenhum erro de JavaScript no percurso; links de produtos e pesquisa continuaram passando nas verificações anteriores do harness.
- Verificação visual executada em `qa-artifacts/v58-attachments/00-mobile-upload-cancel.png`.
- `node --check` e `git diff --check` aprovados.
- Suíte completa: **1.846 aprovados, 4 ignorados e 2 avisos**, em 175,47 s, exit 0. Registro: `vexx-v598-dev/qa-artifacts/attachment-lifecycle-full.log` e `.exit`. Os avisos são de depreciação de mss e timeout do TestClient.

## Arquivos

`public/app.js`, `public/index.html`, `public/interface.css`, `public/sw.js`, `tests/test_attachment_send_lifecycle.py`, `tests/test_frontend_smoke.py` e `tools/chrome_e2e_v58_attachments.py`.

## Limites

Cancelar interrompe o fluxo do cliente e impede o envio posterior da mensagem. Um documento que o PC já tenha recebido pode permanecer em **Documentos**; a correção não apaga dados do servidor. Desconectar depois de uma mensagem já gravada não desfaz a gravação.

As verificações de sessão usam temporização controlada no Node; o cenário visual usa Chrome e celular emulado, sem alegar teste em Android/iPhone físico ou inferência real do modelo. Não houve push, deploy ou reinício do agente nesta etapa; a produção permanece na versão publicada anterior.

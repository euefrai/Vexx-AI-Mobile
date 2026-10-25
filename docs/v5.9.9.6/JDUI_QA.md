# Chrome real, escopo controlado

Executado em Chrome com conta Alice QA, relay FastAPI local, PC Agent real e SQLite temporário. Cancelamento de job real confirmado, SSE HTTP 200, nenhum resultado final e IDs/textos preservados após reload. Depois, fixture com URL MDN explícita, leitura HTTP real e entrega persistida; sem modelo e sem descoberta autônoma.

Geometria em 1280/390/320: root igual ao viewport; larguras de mensagem 760/350/288. Tabela read-only, ordenação por teclado, CSV, reduced motion, zoom CSS 200% com scroll interno e reload aprovados. IndexedDB: três mensagens, uma sessão. Sem pageerror durante os scripts. Link MDN abriu em popup real; fetch offline falhou e `/api/health` voltou a HTTP 200 após reconectar.

As cinco capturas da tabela foram abertas e inspecionadas. A de 390 mostra recorte à esquerda apesar da geometria sem overflow; requer reprodução para distinguir captura/estado de scroll e defeito de layout. Não declarar aprovação visual integral. Zoom mantém acesso às duas colunas por rolagem interna. Emulação de viewport não é teste em telefone físico.

Artefatos: `browser-cancel.json`, `browser-visual.json`, `browser-sources.json`, `coverage-*.png` e `coverage-export.csv`. Capturas/JSONs são desta execução. Sem redesign ou mudança em CSS/HTML.

Pendentes: seis pesquisas completas com modelo/revisão, galeria, todos os exports e fluxos offline/SSE, métricas de duplicação no término autônomo e reprodução do recorte. Não reutilizar provas antigas como validação da versão atual.

Navegador e processos próprios de QA encerrados. `qa-shutdown.json`: PIDs ausentes, banco temporário e runtime removidos; produção não foi reiniciada.

# E2E autenticado local

Chrome real, conta QA alice, PC Agent gratuito real, SQLite temporário; não produção. Sessão do navegador encerrou entre etapas: dois comandos falharam explicitamente por ausência de browser, sessão reaberta e testes retomados. Falhas não foram contadas como passes.

- B Math.hypot sem URL: SSE 200, parcial sem fontes lidas, reload preservado.
- C Math.hypot sem descoberta: entrada de snapshot real, tentativa do modelo real, rejeição numérica, mensagem rj-f3344012eaa4-result persistida.
- Consulta nova Array.prototype.flat: SSE 200, quatro fontes lidas, resultado blocked/timeout, reload preservado; sem alegar síntese aprovada.
- A toSorted: URL explicitamente fornecida por fixture; leitura pública real de duas variantes MDN, resultado parcial extrativo. Cards persistidos após reload e link abriu MDN real.
- Imagens: cinco cards de mídia com origem/licença e aviso de que não são evidência, reload preservado.
- Cancelamento: estado cancelada em 1,132 s; sem resultado duplicado.
- Reconexão: fetch falhou em offline injetado; /api/health retornou 200 após reconectar. Não comprova todos os fluxos offline.
- Exportação MD/CSV: downloads concluídos; IndexedDB com 12 mensagens, cinco estruturadas e quatro resultados.

page_errors=[] nos fluxos concluídos. 401 inicial antes de login é esperado; falhas de rede injetadas são testes negativos, não ausência absoluta de console errors. Logs e e2e-summary.json distinguem fonte conhecida, descoberta e modelo.

Encerramento pedido pelo arquivo qa-stop do harness: supervisor e filho ausentes, SQLite/runtime temporários removidos. Nenhum encerramento de processo de produção.

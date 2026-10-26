# Replay controlado

Ferramenta: `tools/replay_retrieval_v5997.py`, usando o fluxo `research_agents.executar`. `--baseline` carrega oito módulos de `ff486ed` em processo novo. O restante do harness e inicialização SQLite é compartilhado: não equivale a rodar todo o aplicativo histórico.

Captura externa guarda respostas e documentos locais; modo HTML congela também o corpo realmente obtido dentro do leitor. Cada par usa o mesmo SHA-256, pool limitado aos mesmos candidatos e documentos; o extrator de cada versão roda no modo HTML. Nenhuma rede é usada no replay. Não sobrescrever capturas ou resultados. Capturas em `qa-artifacts/v5997/raw/` são privadas/ignoradas; manifesto público contém hashes e contagens, sem republicar páginas inteiras.

Exemplo: `python tools/replay_retrieval_v5997.py --case dev-api --bundle dev-api-html --baseline --output <arquivo-novo.json>`; depois repetir sem `--baseline` com outra saída. Requer o bundle local; o manifesto sozinho não reconstrói o HTML. Textos extraídos não executam o extrator e são rotulados separadamente.

Limites: pool comum por consulta neutraliza qualidade da busca, não a avalia; não representa consultas novas. Navegação fora dos snapshots produz `FROZEN_MISSING`, nunca acesso à rede silencioso. Primeiro replay textual anterior não gravava hash; pares verificados foram reexecutados com a ferramenta final e hashes iguais. Contagens antigas permanecem no manifesto, sem substituição retroativa. Capturas antigas `read_calls=0` tinham instrumentação incompleta; não significam ausência de download.

Resultado e custo: ver `READ_BUDGET.md` e `qa-artifacts/v5997/replay-summary.json`. Ganho operacional consistente nos pares de desenvolvimento; ganho informacional externo não demonstrado. Não medir recall ou causalidade de rede com esse desenho.

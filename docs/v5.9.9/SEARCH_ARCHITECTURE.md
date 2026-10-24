# Caminho de pesquisa V599

Baseline Git: 79c63db, worktree `vexx-v598-dev`. A produção não participa destes testes.

| Etapa | Implementação existente e ajuste |
|---|---|
| Pergunta/intent | `pc_agent.intencao_pesquisa`, `cmd_dados_atuais`, `cmd_pesquisa`. Acrescentados pedidos explícitos com encontre/procure/documentação; notícias usam pesquisa compartilhada; mídia simples retorna resultado, não apenas aviso de job |
| Parâmetros | `query_intelligence.analyze`: local, região, tópico, janela e contrato hard/soft/optional; hoje/ontem/anteontem/última semana |
| Continuação | `conversation_followups.news_request`: até oito mensagens anteriores do mesmo dono/chat, com cutoff da mensagem atual; troca de assunto encerra herança |
| Plano/descoberta | `search_orchestrator.pesquisar`, variantes, fallback, recuperação por manchete/publicador e `ResearchAgentSystem` existentes; nenhuma nova API/motor |
| Seleção | Ranking e deduplicação existentes. Doze candidatos preservados na pesquisa rápida, até seis leituras e três workers, sem aumentar limites de rede |
| Leitura/extração | `research._recuperar_um`, `web_extract`, leitores PDF e metadados existentes; mídia extraída também no caminho síncrono |
| Precisão | `search_verticals.assess` + `fontes_relevantes`; data e demais metadados sobrevivem ao gate final; tópico de notícias preservado |
| Evidência | Evidence Graph, research_events e checkpoints existentes. Novo reservoir diagnóstico limitado no cache; não substitui registros de evidência |
| Redação | Guardas existentes, fallback determinístico e bloqueio de markup de ferramenta não executada; ausência de conteúdo lido encerra com descoberta/limitação, sem pedir ao modelo para preencher lacunas; cards pertencem aos dados recuperados |
| Composição/chat | `research_view`, validadores Python/JS, SSE normal/fallback, mensagem persistida em SQLite e reidratação IndexedDB |

Checkpoints SSE não podem rebaixar completed/failed/cancelled a processing. A reabertura explícita passa por queued, preservando retry. A correção decorre de uma corrida observada no SQLite QA após resposta visual já concluída.

Perdas reproduzidas: datas removidas antes do gate final; pergunta sobre cidade não reconhecida; tópico eliminado da busca; metadados de mídia não atravessavam a pesquisa rápida; prompt negava busca de imagens; visual iniciava job sem mostrar galeria no chat; verbo “usar” exigido literalmente em documentação inglesa; pedidos “encontre” não pesquisavam; imagens secundárias de páginas viravam galerias sem intenção de mídia.

O contrato novo torna explícitos parâmetros já suportados. Não é um extrator universal de todas as preferências/negações/entidades. Shopping mantém seus critérios próprios existentes. Desambiguação mundial de homônimos e verificação semântica ampla continuam limitadas; não há alegação de cobertura absoluta.

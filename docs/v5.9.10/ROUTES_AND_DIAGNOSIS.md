# Rotas e diagnóstico V5.9.10

Inspeção do checkout real, base `6d73e48`; referências de implementação após `a03d67d`.

| Fluxo | Caminho real | Componentes e limites |
|---|---|---|
| Conversa | `server.py:2215` POST `/api/ai/stream` → relay → `pc_agent.ai_stream_worker` | Intenção e contexto do chat; não força Research Agents. Saudação tem resposta determinística. |
| Web normal | `pc_agent.py:2022` em diante → `research.pesquisa_rapida` (`research.py:1214`) | Orchestrator, Query Intelligence, provedores e leitor existentes. Grounding no prompt normal; não usa `research_synthesis.generate`. |
| Web aprofundada síncrona | `research.pesquisa_aprofundada` (`research.py:1613`) | Mesmo chat/grounding, investigação limitada; não equivale ao job Research Ultra. |
| URL explícita | `research.analisar_url` (`research.py:1564`) | URL pedida pelo usuário, validação pública/SSRF, extração e passagens; não é descoberta. |
| Pesquisa em background | `/api/research/start` (`server.py:1871`) ou comando de pesquisa profunda no chat → `iniciar_job_bg` → `_job_worker` (`pc_agent.py:4578`) | Research Agents → Query Intelligence → provedores/orchestrator → leitores → Evidence Graph → Gaps → síntese/revisão → auditoria/checkpoints. O chat evita a busca síncrona duplicada para esse comando. |
| Entrega | `/api/research/status`, `/stream`, `/view`, `/export`; `_persistir_resultado_pesquisa` | Job e resultado no SQLite; mensagem com JDUI chega ao chat, sincroniza com IndexedDB e reaparece após reload. Eventos são vinculados ao dono/job. |
| Shopping | Intenção própria no PC Agent → `shopping.py` (`buscar_web_v55`, `buscar_com_fallback`) | Usa orchestrator em parte da descoberta. Mantém preços/variantes e pipeline próprio; não migrou para Research Agents. |

Compartilhados de fato: `query_intelligence.py`, `search_orchestrator.py`, `search_providers.py`, leitores em `research.py`/`web_extract.py`; `research.py` também consulta Evidence Graph ao aproveitar passagens. Gaps, checkpoint de investigação e redação/revisão estruturada são próprios do fluxo agêntico. JDUI também apresenta resultados de mídia e outros recursos fora desse fluxo. Não existe um único pipeline universal.

Instrumentação em `probe_discovery_v5910.py` envolve o `search_providers.buscar` real, além do wrapper externo do probe. Na reprodução Bosch, DDG retornou seis candidatos para “Bosch Fundadores” e “Bosch Data de fundação”; a trilha de “Bosch Produtos” passou por resultados vazios em provedores e chegou ao Bing, que encontrou sites oficiais. Portanto, nem todo vazio final nasce no provedor: houve descoberta e leitura, seguidas de perda de relação/passagem. No produto Sony, títulos com A7IV/A7 IV foram rejeitados em parte como entidade divergente apesar do potencial de relevância. Esses aliases não foram liberados sem prova de identidade/variante.

## Perdas comprovadas e correções

- **Requisitos/consultas:** criador + “quando”, perguntas causais naturais e “retorno” podiam perder facetas ou manter conjunções na entidade. Produtos numerados ativavam a preservação integral da pergunta. Evoluído o parser existente; compactação somente para peso/bateria sem outras restrições. Condição bateria/cartão permanece em todas as subconsultas. Negação, variantes, datas, orçamento e local mantêm a proteção. Não foi criado parser/motor paralelo.
- **Depois da leitura:** na reprodução anterior Bosch, busca encontrou página com fundador/ano/produtos, mas relações em tabela não sobreviviam ao contrato do reader. `research_agents.py` passa as tabelas já extraídas; `evidence_graph.py:191` recupera somente rótulo/valor literalmente presentes e cabeçalho da entidade exata. Suporte é parcial, spans referem o texto realmente retornado. Não fabrica span do documento integral nem corroboração independente.
- **Gaps:** regressão reproduzível confirma que fundador/ano já resolvidos deixam somente produtos pendentes. Não foi necessário alterar o controlador, limites ou anti-loop.
- **Transporte:** `hermes_bridge.py:136` normaliza content parts de texto; antes `str(list)` invalidava JSON correto. `chat_complete` agora conserva finish reason/usage seguros antes de rejeitar saída vazia. O writer classifica truncamento/filtro informados, sem substituir resposta por reasoning ou liberar saída inválida.
- **Galeria:** sync chama `renderMessages()` e substitui mensagens. Chrome reproduziu foco normal=true, remount=false, opener desconectado=true. Restauração usa escopo dono/conversa/mensagem/componente e URL da mesma mídia; remount=true após correção. Não muda o design nem toma foco de outra conversa.
- **Ciclo de vida:** tailer aguardava indefinidamente jobs `interrompida`/`pausada`, bloqueando drain. QA autenticado com timeout de síntese expôs o problema. Regressão antes: 2 falhas/4 pass; após: 6 pass, e grupo runtime/research: 39 pass. Thread encerra depois de entregar eventos pendentes nesses estados; retomada cria seu próprio worker/tailer.

## O que não foi resolvido

O ranking não foi relaxado para aumentar a contagem. No rerun externo Bosch, foram lidas homepages/páginas oficiais de produtos, sem passagem válida; não reproduziu o ganho do corpus fixo. Sony tem aliases legítimos que ainda encontram barreiras de entidade. Comparação e pedidos históricos com instruções adicionais ainda contaminam a entidade; novas categorias não têm esquema de requisitos suficiente. Esses problemas ficaram visíveis no holdout e não foram ajustados após abri-lo.

A falha antiga de reconexão Windows não foi reproduzida: teste isolado passou em 8,13s; suíte também passou mantendo `ready.wait(15)`. Acrescentados fases e log à mensagem de falha. Isso não prova a causa daquela intermitência. O vazamento de tailer é outra falha comprovada de ciclo de vida, não uma explicação retroativa para a reconexão antiga.

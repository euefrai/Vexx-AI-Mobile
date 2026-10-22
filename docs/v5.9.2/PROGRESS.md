# V5.9.2 — progresso

HEAD inicial: cccd8b5, checkout limpo. Sem push/deploy. Skill token-efficient aplicada.

A: baseline universal externa concluída em qa-artifacts/v592/baseline-universal.json (7 casos, fontes sem correspondência). Baseline comercial/científica preservada em v591. Reproduções adicionais: replanejamento mantinha finais feitas; snippet explicitamente não lido sustentava afirmação.
B/C: replanejamento invalida derivados, respeita orçamento restante, preserva modelos/unidades, avalia ganho por rodada, interrompe recuperação sem ganho; snippets explicitamente não lidos excluídos do suporte. Síntese do checkpoint agora exposta no resumo. 61 testes focados passaram; seguir com cobertura universal e validação de apresentação.

Contratos: ResearchAgentSystem usa research_jobs/research_evidence/events + ResearchContextStore; orçamento e cancelamento existentes. Search Orchestrator e downloader SSRF continuam centrais. research_view gera somente componentes JDUI validados (Python/JS). live_data já roteia clima/hora/notícias; moedas ainda não são suportadas. Nenhum novo motor paralelo.

Pendentes: cobertura universal e datas relativas; câmbio real; fontes/JDUI; Chrome desktop/mobile e replay/reload; benchmark universal e convencional; suíte completa final; relatório e docs requeridos.

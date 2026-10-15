# JÚLIA Research Agent Coordination (V4.7)

Papéis continuam funções (sem processos por agente). Coordenação real:

- Tarefas: etapas do plano com id, tipo, alvo, tentativas.
- Progresso: eventos por etapa (`step_started` + conclusão por tipo).
- Dificuldades: `job.erros` + eventos `falha`/`alerta` por etapa.
- Novas buscas: follow-ups de investigações agendados no replan.
- Lacunas: `_lacunas` + métricas `pendencias`.
- Replanejamento: proposto pelo orchestrator, executado com teto.
- Conclusão/cancelamento seguros: estados finais + limpeza de workers.
- Permissões por papel: search→provedores; analyst→downloads (SSRF);
  checker/auditor→só leitura de evidências; orchestrator→plano e
  orçamentos; nenhum agente toca rede privilegiada, arquivos ou controle
  remoto (sem código para isso; sem credenciais no caminho).

Paralelismo: workers de job (teto global 2) + tailer de eventos; leitura de
páginas sequencial por job (PC modesto). Provedores com métricas
(ok/falhas/ms) por job; fallback DDG→SearXNG; SearXNG sem instância =
indisponível declarado.

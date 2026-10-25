# VEXX AI V5.9.9.6 — implementação parcial / NO_GO

Base: `39644ca`, branch local `codex/v598-autonomous-research`.
HEAD final de implementação: `1df28b3`; commits `592edd2` (contexto) e `1df28b3` (transporte/QA). O commit posterior de documentação e artefatos não altera o código do motor testado.

## Resultado

Corrigida a fragmentação de consultas que retirava a entidade de atributos como sintaxe, retorno, fundadores e consequências. A Query Intelligence agora fornece contexto às subconsultas e ao replanejamento. Datas, quantidades, localidades, variantes e exclusões usam conservação do pedido quando não há decomposição segura. A análise salva precisa corresponder ao objetivo do job.

Adicionado trace opcional e limitado de QA: seleção/cobrança, extração, rejeição, descoberta e armazenamento. Referências protegidas por hash; sem credenciais, URLs ou conteúdo privado. O contrato completo de trace ainda não foi implementado.

**Não pronto para publicação.** Na comparação externa Math.hypot, as consultas passaram a conservar a API, mas a candidata terminou com zero evidências utilizáveis após 12 extrações rejeitadas. A baseline tinha quatro registros lidos, sem auditoria factual independente. Não foi demonstrado ganho consistente de recuperação.

Foram executados depois mais dois casos: Bosch, zero evidências, e Revolta da Vacina, uma fonte lida. Não houve síntese aprovada nem comparação congelada nesses casos. DEV Object.assign armazenou três evidências de sintaxe; retorno/comportamento continuam sem cobertura. Não há justificativa para mudar a decisão NO_GO.

## Arquivos de implementação

- `query_intelligence.py`: contexto conservador, fronteiras de consultas, entidade de fundação, retorno de API.
- `research.py`: divisão delega a preservação de contexto à Query Intelligence.
- `research_agents.py`: contexto no plano/replan/envio, descarte de request incompatível e eventos opcionais de trace.
- `evidence_graph.py`: relação literal de valor retornado, sem relaxar outras relações.
- `retrieval_trace.py`: observação opt-in e limitada com referências protegidas.
- `tests/test_context_lock_v5996.py`: planejamento, envio real a provedor controlado, replan, request incompatível, relação de retorno, privacidade/limites e orçamento observado.
- `benchmarks/context_lock_v5996*.json`: 32 perguntas de planejamento e oito perguntas externas; não são gold independente.
- `tools/probe_context_v5996.py`: diagnóstico externo com SQLite temporário e comparação isolada de módulos históricos.

## Validação

Reprodução anterior: 31 falhas / 9 aprovações; primeira correção: 40 aprovações. Após corrigir regressões, suíte de `592edd2`: 1670 passed, 4 skipped. Suíte final do motor `1df28b3`: **1672 passed, 4 skipped, 2 warnings em 298,70 s**. Focados de transporte: 112 aprovados. Consultar `qa-artifacts/v5996/validation-summary.json`, gerado dos logs executados. Avisos existentes de mss e TestClient; nenhum teste foi retirado ou mascarado.

As primeiras rodadas completas encontraram regressões reais. A proteção rígida impedia reformulações compactas/científicas; isso foi ajustado preservando os testes existentes. O trace também assumia ID de etapa obrigatório em chamadas diretas; passou a aceitar referência ausente. Nenhum teste anterior foi removido ou relaxado.

Baselines controladas: Search 34/34, Shopping 59/59, Experience 16/16. Não são validação de pesquisa externa nem síntese científica.

Os probes externos não têm modelo, UI nem autenticação. Os JSONs preservam consultas realmente enviadas, contadores e estados; não publicam páginas completas. O corpus externo foi congelado depois da correção inicial e antes de sua avaliação, limitação explícita. Não houve replay completo com respostas idênticas.

Separadamente, diagnóstico real com modelo gratuito chegou à revisão, que recebeu rate limit; síntese não aprovada. Chrome autenticado comprovou cancelamento/SSE/reload e a entrega controlada de fontes/tabela/CSV em SQLite temporário. Cinco screenshots foram inspecionadas; o recorte em 390 permanece pendente. Os testes com URL explícita não são sucesso autônomo. Detalhes em REAL_MODEL_E2E.md e JDUI_QA.md.

## Pendências obrigatórias

Completar propagação interna de contexto e contrato query→requisito; corrigir desperdício de leituras repetidas sem perder facetas; completar ranks/provedor/vínculos até síntese e leitores alternativos; replay de mesmos dados; novo holdout independente; seis E2Es com modelo/revisão disponível; galeria/exports/fluxos offline e reprodução do recorte 390. Detalhamento e próximo passo em `docs/v5.9.9.6/PROGRESS.md`.

Sem push/deploy, reinício de produção, alterações de identidade/permissões ou uso de banco real. A etapa fica em commits locais; a versão permanece **NO_GO**.

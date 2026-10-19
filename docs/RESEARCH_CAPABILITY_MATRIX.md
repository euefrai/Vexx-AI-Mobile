# Matriz de capacidades — Research Engine (V5.7 FINAL, 2026-10-18)

Estados: **FUNCTIONAL** (verificado com evidência real), **PARTIAL**
(funciona com limitação conhecida), **BLOCKED** (recusa externa honesta),
**BROKEN** (defeito aberto), **NOT_IMPLEMENTED**, **NOT_TESTED** (sem
evidência nesta rodada). Nunca marcar pronto só porque teste unitário passou.

| # | Capacidade | Estado | Evidência | Limitação / pendência |
|---|---|---|---|---|
| 1 | Busca orquestrada multi-provedor | FUNCTIONAL | Smoke real: `estado=ok`, bing saudável, 3 fontes abertas (4,2s); bench pesquisa 34/34 | Cobertura depende dos provedores saudáveis do dia |
| 2 | Provedores externos bloqueados (MLB/Magalu/DDG) | BLOCKED (externo) | 403/bot-wall registrados como bloqueio, nunca "sem resultados" | Não contornado por regra; sem proxy/CAPTCHA |
| 3 | Recuperação de páginas + extração de artigo | FUNCTIONAL | 3/3 abertas com conteúdo; Wikipédia extraída | Extração determinística tem resíduos (sidebar/marcação) em páginas grandes; trafilatura não instalada |
| 4 | Grounding com conteúdo lido | FUNCTIONAL (novo) | `texto_lido` ≤1.200 ancorado no trecho relevante; bateria 16/16; smoke: grounding 4.388 chars | Página só encontrada mantém trecho ≤400 marcado "NÃO lida" (por design) |
| 5 | Leitura de página pedida pelo usuário (URL) | FUNCTIONAL (novo, mínimo) | `url_pedida` conservador + `analisar_url` (mesmo `baixar`) + aviso honesto; smoke Wikipédia aberta / Magalu bloqueada | Só 1 URL por mensagem; sem crawling |
| 6 | Documentos (PDF/DOCX/TXT/MD/CSV/TSV/XLSX/HTML/JSON) | FUNCTIONAL | docs_agent (uploads/WS) ligado; bateria `contrato.txt`/`vendas.csv` | — |
| 7 | OCR de PDF escaneado | NOT_IMPLEMENTED | Ausente por design | Sem OCR inventado; sinalizar limitação ao usuário |
| 8 | Tabelas/planilhas em documentos | PARTIAL | XLSX/CSV suportados no docs_agent; bateria cobre CSV | Célula-a-célula em exibição não testada nesta rodada |
| 9 | Evidências/claims (fence) | PARTIAL | SUPPORTED/PARTIALLY/INSUFFICIENT/UNVERIFIED com quantidade+unidade e tokens; suíte cobre | Sem promoção FETCHED→VERIFIED (correto); integração contínua no chat parcial |
| 10 | Source validation (link/imagem) | PARTIAL | Consumido pelo shopping (veredito) | Pesquisa geral não gera veredito de link/imagem (auditoria V5.7) |
| 11 | Shopping real (ofertas confirmadas) | FUNCTIONAL | Smoke real: **2/2 confirmadas na página do item**, com URL e preço (KaBuM, 41,5s); bench 59/59 | — |
| 12 | Filtro de orçamento numérico | PARTIAL | Produtos ≤R$300 atendidos; preço exibido em texto | `preco_valor` numérico ausente nos 2 cards do smoke → gate não age nesses casos |
| 13 | Comparação de produtos | PARTIAL | Cards comparativos JDUI existem e são validados | Não exercitada em smoke real nesta rodada |
| 14 | Agentes de pesquisa/hipóteses | PARTIAL | `/research` + hypothesis_engine cobertos pela suíte (SSE/replay) | Hipóteses só em jobs, não no chat síncrono |
| 15 | SSE/continuidade | PARTIAL | Fases reais no shopping; reconexão/replay testados | Risco de duplicação no tail-emit (`pc_agent.py:3951-3957`) documentado |
| 16 | Métricas/observabilidade por provedor | PARTIAL | `metricas_provedores()` com latência/erros/vazios/bloqueios | Sem chamador em produção (só diagnóstico) |
| 17 | JDUI paridade backend×frontend (produto) | FUNCTIONAL | 3 correções + harness Node (falha antes/passa depois); suíte | Outros componentes cobertos pela suíte, sem auditoria campo-a-campo nesta rodada |
| 18 | JDUI em navegador real (Chrome mobile/desktop) | NOT_TESTED | — | Validação visual manual pendente (exigida pelo brief; não executada) |
| 19 | Segurança (SSRF/DNS/redirects/limites/bloqueios) | FUNCTIONAL | URL do usuário passa pelo mesmo `baixar`; suíte de segurança intacta | Sem bypass de bot-wall em nenhum caminho |
| 20 | Performance (tempos reais) | FUNCTIONAL | Busca 4,1s; URL 2,3s; shopping 41,5s; prompt+página 2,5s | Render Free preservado (gates/limites existentes) |
| 21 | Serviço publicado (Render) | NOT_TESTED | Sem deploy/push autorizado nesta rodada | Distinguir sempre local × publicado (E2E) |
| 22 | Respostas via LLM (Hermes) | PARTIAL | Hermes disponível: porta 8645, `/v1/models` HTTP 200 (DeepSeek V4.1 Flash) | Não exercitado no smoke (custo não autorizado); qualidade de resposta não medida |

## Como ler esta matriz

- FUNCTIONAL exige evidência externa ou determinística reproduzível, não só
  teste unitário.
- PARTIAL/BLOCKED são estados honestos e aceitos; BROKEN fica vazio nesta
  rodada porque os defeitos priorizados foram corrigidos (ver progresso).
- A rodada não expandiu escopo: achados fora do GAP (SSE, métricas, source
  validation geral, navegador real) ficam registrados aqui para as próximas.

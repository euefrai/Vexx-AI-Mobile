# VEXX AI V5.9.11 — Query-to-Evidence

**Decisão: NO_GO para Research Ultra.** Há ganhos reproduzidos de requisitos, vínculos e integração, mas descoberta externa e conclusão de pesquisas continuam insuficientes. WEG produziu redação LLM, revisão, citações literais e persistência no Chrome autenticado; o resultado continua parcial, sem comprovação de confiabilidade ampla.

## Estado

27/10/2026, worktree `vexx-v598-dev`, branch `codex/v598-autonomous-research`. HEAD inicial `0959e8c`, árvore rastreada inicialmente limpa; arquivos não rastreados anteriores preservados.

Commits locais: `daca55b` congela holdout; `71fab67` implementa contrato/vínculos/catálogo literal; `3de4932` corrige fronteiras DDG/estado da síntese; `17f9844` fecha ferramentas QA e placeholder mobile. O commit que contém este relatório fecha a entrega; consultar sua identidade com `git log -1 --oneline`.

Sem push, deploy, reinício de produção, alteração do SQLite real, extensão Júlia, Fajulto Studio ou VERY. Identidade Lucas preservada. QA usou contas descartáveis, FastAPI/PC Agent de desenvolvimento e SQLite temporário. Modelo real exclusivo: `poolside/laguna-s-2.1:free`, sem fallback pago.

## Causas reproduzidas e mudanças

| Problema | Reprodução | Correção e limite |
|---|---|---|
| Zero requisitos ou parte ignorada | Três capturas V5.9.10 sem requisitos; grupo inicial: 9 falhas/2 passes | `requirement_contract` conserva objetivo original pendente se não conseguir decompor ou reconhecer toda a demanda. Objetivo não recebe suporte factual. |
| Facetas/entidades perdidas | Comparações, geografia e definições sem vínculo; assunto contaminado por instrução | Extensão do Query Intelligence existente: facetas, entidades por opção, separação de instruções. Linguagem natural universal permanece pendente. |
| Exigência de fonte oficial ignorada | Definições privadas podiam cobrir atributos reconhecidos | Restrição `source_authority` pendente, sem presumir autoridade por domínio/título. |
| Tema confundido com resposta ou cache obsoleto | Outra entidade/direção e passagem salva incompatível com texto atual | Relação literal e sujeito compatível; documento/passagem/offsets preservados. Revalidação contra texto integral quando disponível; compactação conserva IDs. |
| Estado NOT_SEARCHED com evidência fornecida | Reprodução específica falhou antes da correção | Síntese deriva estados do conteúdo efetivamente oferecido ao redator. Não confirma objetivos não decompostos. |
| Citações incompatíveis do modelo | Contraste real A/B/C rejeitado | Catálogo opt-in de IDs de trechos literais, resolvidos antes dos validadores existentes. Mantém revisão real separada, limites e rejeições numéricas. |
| DDG herdava snippet do próximo resultado | Dois negativos falharam: anúncio ocupando limite e snippet cruzando âncora | Snippet limitado ao resultado; anúncios `/y.js` filtrados antes do limite; motivo explícito para candidatos antigos no orquestrador. Sem ganho de fonte útil demonstrado pelo replay. |
| Título “Company” | Tipo estruturado tratado como título | Tipo genérico deixa de ser título plausível; QA exibiu título real WEG. |
| Placeholder cortado em 320 px | Inspeção visual encontrou quebra após primeiro encurtamento | Texto final “Mensagem…”, verificado novamente em Chrome e com 37 testes focados. |

Nenhum novo motor, parser paralelo, Evidence Graph, provedor, banco ou agentes. Limites de consultas/páginas/texto/tokens/timeouts não aumentaram. O catálogo reutiliza o orçamento existente. Replanejamento permanece orientado pela matriz existente, com anti-loop/orçamento e encerramento parcial quando não há suporte.

## Replays controlados

Mesmos registros extraídos V5.9.10, sem rede, nova extração, ranking ou modelo:

| Caso | Vínculos antes → depois | Resultado |
|---|---:|---|
| Rio Paraguaçu | 0 → 1 parcial | Rótulo literal de foz recuperado; demais facetas pendentes. |
| Bacharelado/licenciatura/tecnólogo | 0 → 19 | Definições de diferentes documentos; não são 19 fatos independentes. Restrição oficial continua pendente. |
| Seleção feminina de vôlei | 0 → 0 | Futebol/agenda não promovidos a resposta de vôlei. |

Hashes iguais por caso em `read-before-summary.json`/`read-after-summary.json`. Isso demonstra vínculo, não descoberta nem verdade independente da fonte.

Replay de candidatos: pool real congelado de 11 URLs, oito registros, mesmos primeiros candidatos e orçamento. Antes/depois: sete tentativas de leitura, **zero fontes lidas retidas**, peso/bateria sem suporte. Anúncios passam a ter motivo de rejeição; o replay injeta pool pronto e não reexecuta o parser DDG. Não demonstrou economia de slots, ganho de ranking ou síntese melhor. Testes HTML comprovam a correção local de snippets/anúncios. Páginas de verificação de conta e páginas genéricas não responderam à pergunta. Consultas/candidatos/documentos em `provider-trace-summary.json`.

## Holdout externo

16 perguntas inéditas congeladas em `daca55b`, antes da implementação. Sem URL semeada e sem modelo nesta trilha. Anotações do agente, sem gold humano. Código avaliado `71fab67`, hashes por módulo preservados. Correções posteriores em `3de4932` não foram reavaliadas nesse holdout; não atribuir a elas seus resultados.

- Quatro perguntas retiveram alguma entrada: sete entradas ao todo, **somente uma marcada como efetivamente lida**.
- Apenas Embraer teve passagem vinculada: uma passagem literal com dois vínculos diretos, fundador e fundação; produtos pendentes. Inspeção confirmou relação explícita com a empresa.
- Nove perguntas conservaram objetivo original não decomposto. História ainda gerou entidade incorreta “Quais foram as”. Cultura, esporte, ambiguidade e algumas restrições continuam insuficientemente interpretadas.
- Zero pesquisas completas. Não houve redação de 16 respostas finais nesta trilha.
- 188 chamadas observadas no nível externo e 243 internas: níveis diferentes, **não somar como chamadas independentes**. 151 extrações observadas, 143 não vazias; podem repetir fontes e não representam 151 páginas únicas úteis.
- Mediana 17,288 s, intervalo 9,335–32,465 s; não é estimativa de latência de produção.

Não comparar causalmente os quatro casos com entradas aos três de outro holdout. Não há precisão/recall global nem prova universal de ausência de falsos suportes. `holdout-summary.json` conserva perguntas, consultas, estados, proveniência, IDs e hashes.

## Modelo real e autenticação

Contraste A direto / B agente / C endpoint QA: mesma fonte pública conhecida Math.hypot, catálogo literal, uma tentativa por caminho em `71fab67`. Requests A/B iguais; objetivo, sistema e quotes B/C iguais. Modelo efetivo gratuito confirmado, HTTP 200 com conteúdo e `finish_reason=stop` nos três caminhos.

- A: `quantity_mismatch`; acrescentou uso 2D/3D com citação que não sustentava a afirmação. Não demonstra falso positivo do validador.
- B: `invalid_paragraph`; excedeu limite de três referências no parágrafo.
- C: `quantity_mismatch`; afirmou retorno zero sem esse valor no trecho citado; outro parágrafo também excedia referências. Resultado parcial preservado, redação rejeitada.
- Não se reproduziu HTTP 200 vazio ou timeout no contraste. Causa do vazio histórico continua indeterminada. Validação numérica não foi afrouxada; contraste não foi repetido até passar.

No QA posterior em `3de4932`, WEG foi descoberta sem URL fornecida, teve uma fonte lida, dois parágrafos redigidos e duas avaliações `SUPPORTED` do revisor real. E1/Q1 e E1/Q3 foram resolvidos em citações literais. Escrita: 4,739 s / 1.586 tokens totais; revisão: 3,775 s / 1.916 tokens. Fluxo observado em 31,666 s, persistido após reload.

**Outcome partial:** matriz cobre fundador/ano, mas não reconhece a relação inglesa “manufacturers of” sobre produtos. A informação está no payload do redator/revisor; o card exibe excerto abreviado. Não confundir corte visual com ausência de evidência no payload, nem revisão LLM com gold independente. Ver `live-synthesis-summary.json`.

## Chrome, JDUI e armazenamento

Nove cenários com Chrome real, autenticação QA e backend/agent reais: saudação, factual, empresa, história, notícia, comparação, múltiplos requisitos, imagens e cancelamento. Todos preservaram mensagens após reload; nenhum `pageerror` capturado. Saudação não abriu pesquisa profunda; cancelamento terminou `cancelada`. História/comparação/Adidas ficaram parciais sem fonte útil; factual/notícia mostraram limitações. Não contar esses fluxos como respostas aprovadas.

- Cards/galeria sem overflow em 1280/390/320 px. Fonte aberta em popup real na Wikipedia.
- Primeira imagem pública carregada; teclado e retorno de foco aprovados. Screenshot do segundo item foi capturado carregando; não prova carregamento de todas as imagens.
- Zoom 200%, movimento reduzido, metadados após reload, fetch offline rejeitado e health 200 após reconexão. Emulação de viewport, não celular físico.
- Exportações MD/CSV reais. IndexedDB: 22 mensagens / 22 IDs únicos, cinco mensagens estruturadas, quatro resultados. SQLite: 22 IDs únicos, `quick_check=ok`.
- Console: 401 de sessão anônima antes de login e erros esperados durante offline; aviso de senha fora de formulário permanece. Não se declarou console literalmente vazio.
- Uma repetição do harness fechou metadados já abertos e falhou pela premissa do teste; harness tornou-se idempotente, execução final passou e log da falha foi preservado.

Publicação da fonte segue identificada como publicação, sem conversão em data de fundação/evento. Fixtures, replays, internet e QA autenticado têm escopos distintos nos sumários.

## Testes, segurança e recursos

Baseline histórico V5.9.10: 1.754 passes / quatro skips / dois warnings; não é nova execução integral do checkout antigo. Foram adicionados 21 casos, sem retirada de testes.

- Suíte completa final de lógica: **1.775 passed, 4 skipped, 2 warnings**, 476,95 s, exit 0, `full-release.log`.
- Execução intermediária falhou com `KeyError: evidence_id` no adaptador mínimo com `id`; corrigido fallback e suíte integral seguinte passou. Execução anterior com 1.772 passes não é a final. Logs de falhas preservados.
- Grupos focados de etapas: 105, 85, 75, 108 e 84 passes; sobrepostos, não somar.
- Após última mudança somente de placeholder: **37 passes**, 5,55 s, exit 0, Chrome repetido. Suíte integral não repetida por alteração textual.
- Search 34/34, Shopping 59/59, Experience 16/16; regressão, não avaliação inédita de pesquisa autônoma.
- `py_compile`, `node --check` das ferramentas e `git diff --check` aprovados. Dois warnings de depreciação existentes: mss/TestClient timeout.
- Suíte preserva testes de escopo por usuário, URLs/SSRF, permissões e validação JDUI/síntese. Novos negativos: entidade/variante, número/unidade, ID inexistente, passagem descontínua e cache obsoleto. Sem pentest externo.
- Nenhum código do modelo executado, CAPTCHA/paywall contornado ou credencial publicada. Páginas/payloads integrais e reasoning não integram artefatos públicos.
- Sessões QA C/bootstrap/live encerradas, bancos/runtime temporários removidos e zero processos associados. Zero operações ativas antes do último stop; nenhum agent de produção encerrado.

## Gates e continuidade

| Gate | Decisão |
|---|---|
| A Requirements | PARCIAL: preserva incerteza, mas algumas entidades/demandas ainda falham. |
| B Evidence links | Ganho localizado comprovado; produtos/outras relações pendentes. |
| C Source discovery | NÃO APROVADO: sem ganho controlado de fonte útil no replay de candidatos. |
| D Coverage | Melhoria conservadora nos casos testados, sem interpretação universal. |
| E Replay | Ganho de vínculos sob entrada idêntica; sem ganho de seleção demonstrado. |
| F External | NÃO APROVADO: só uma pergunta com passagem vinculada. |
| G Synthesis | MARCO PARCIAL: WEG citada/revisada/persistida; contraste técnico rejeitado. |
| H End-to-end | NÃO APROVADO: nenhuma pesquisa autônoma completa aprovada. |
| I JDUI | APROVADO no QA local executado, sem alegar produção/celular físico. |
| J Security | Nenhuma regressão crítica detectada nas verificações executadas. |

Produção alterada: Query Intelligence, Evidence Graph, agentes/síntese, research/orquestrador, integração PC Agent, título e placeholder. Testes, ferramentas e novos conjuntos de desenvolvimento/holdout complementam a entrega. Lista exata: `docs/v5.9.11/CHANGES.md`; comandos/limites: `docs/v5.9.11/REPRODUCTION.md`; sumários/hashes: `qa-artifacts/v5911/`.

Próximo passo exato: reproduzir perdas de produto/entidade/restrição e seleção em corpus novo de desenvolvimento, com fontes pertinentes anotadas. Corrigir a etapa responsável, congelar **outro** holdout e exigir pesquisa completa real seguida de casos independentes. Não usar este holdout para ajuste ou transformar ausência de suporte em sucesso.

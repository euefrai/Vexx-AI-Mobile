# Pesquisa profunda — navegação por seções e persistência

Base: `19382a6`, branch `main`. Alterações locais; sem push, deploy, reinício do PC Agent ou acesso ao SQLite real.

## Problemas e correções

- O seletor de documentos longos dependia de palavras do corpo. Agora títulos pertinentes e sua hierarquia ajudam a selecionar parágrafos/listas, incluindo seções de antecedentes e desdobramentos. Mantidos os tetos de 8 passagens e 8.000 caracteres, além do teto existente de texto de evidência na síntese. A nova hierarquia acrescenta metadados de contexto.
- Um H1 real pode ficar no cabeçalho do artigo, fora do contêiner extraído. Esse assunto agora acompanha as passagens quando o contexto estrutural permite, sem herdar títulos de navegação, cabeçalhos do site ou outro artigo. Títulos dentro da extração mantêm offsets/hash dessa extração; H1 externo usa explicitamente coordenadas do próprio texto DOM normalizado e um hash de vínculo com o corpo. Não são offsets do HTML nem posições inventadas no corpo.
- A hierarquia de seção chega às evidências, ao EvidenceGraph e ao contexto da síntese. Assunto exato + seção pertinente fornece apenas `PARTIAL_SUPPORT`: título não comprova causalidade nem resposta completa. Variantes, fontes não lidas, abstracts e metadados continuam sujeitos aos controles existentes. Negação, condicionais e outro sujeito não são promovidos a suporte direto pela nova regra.
- Mais trechos úteis expuseram duplicação em `scientific_sections`, `sections`, `trecho_usado` e hierarquias. Registros grandes agora usam referências internas para dados exatamente repetidos. A leitura restaura os campos, aceita registros antigos e conserva o limite de 12.000 caracteres. Não há truncamento de JSON, descarte silencioso de evidências ou ampliação do limite; conteúdo único excessivo continua rejeitado.

## Evidência observada

Replay do mesmo HTML de desenvolvimento já capturado para Guerra do Contestado, SHA-256 `0f6c110685fa5564b1c6d311f119bcc8215a3f518e8e7e934cc479aea17f8a27`, comparado à base `19382a6`:

| Medida | Antes | Depois |
| --- | --- | --- |
| Caracteres selecionados | 1.727 | 651 |
| Passagens vinculadas aos requisitos | 0 | 8, todas parciais |
| Estado de causas/consequências | DISCOVERED | PARTIALLY_SUPPORTED |

No analista atual, a fonte original foi retida e recarregada do SQLite temporário com três passagens selecionadas, sem falhas de grafo. Continuou incompleta. A ferramenta recusa URLs sem captura; não reaproveita HTML de uma URL como evidência de outra.

Isso comprova recuperação de contexto antes perdido nesse documento, com menos texto retido. Não é evidência de descoberta externa melhor, confirmação causal, menor latência geral ou pesquisa universal completa.

## Testes

- Baseline dos testes novos: 6 falhas e 7 aprovações; os erros incluíam perda de parágrafos, hierarquia e vínculos. A primeira integração também reproduziu `JSONLimitError` com passagens longas; corrigido por deduplicação exata.
- Focados finais: **117 passed, 1 skipped, 1 warning**, 22,24 s. Incluem 22 casos novos, leitura longa, offsets/hash, variantes, isolamento por usuário, persistência/reload, propagação à síntese, compatibilidade de metadados e revisão semântica existente.
- Suíte completa final: **1.868 passed, 4 skipped, 2 warnings**, 167,01 s, exit 0. Avisos existentes de depreciação de `mss.mss` e timeout do TestClient. `py_compile` e `git diff --check` aprovados.
- Replay local: `qa-artifacts/section-context-replay-final.json`. Focados: `qa-artifacts/section-context-final-focused.log`. Suíte final: `qa-artifacts/section-context-full-final.log` e `.exit`.

## Arquivos

`web_extract.py`, `evidence_graph.py`, `research_agents.py`, `tests/test_research_section_context.py`, `tools/replay_research_sections.py` e este relatório.

## Limites e próximo passo

A — leitura: validada com fixtures e replay do HTML real salvo, sem nova coleta.

B — descoberta: não reavaliada ao vivo nesta etapa. Nenhuma URL esperada foi incorporada à lógica de produção.

C — síntese: contratos existentes e propagação de contexto testados com funções controladas; sem inferência real ou teste autenticado no chat de produção. Não houve teste visual nesta etapa de backend.

Próximo passo: avaliar descoberta e síntese reais em um conjunto pequeno de perguntas novas, separando falhas de coleta, seleção e revisão. Contexto parcial permanece parcial até confirmação com trechos e revisão vinculados aos requisitos. Não declarar a pesquisa completa apenas por aumentar o número de testes.

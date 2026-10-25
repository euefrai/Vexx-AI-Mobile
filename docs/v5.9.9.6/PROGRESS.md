# V5.9.9.6 — checkpoint local, não concluída

Base: `39644ca`, branch `codex/v598-autonomous-research`, checkout `vexx-v598-dev`.
Não houve push, deploy, reinício de produção ou escrita em banco real.

## Implementado nesta etapa

- Reprodução anterior: 31 falhas / 9 aprovações em 40 testes novos.
- Corpus de planejamento com 32 perguntas; preservação de entidade, operações qualificadas, localidades, datas, unidades, exclusões e títulos contendo termos visuais.
- Contexto central reaproveita Query Intelligence; divisão por vírgula/conjunção deixa de separar atributos da entidade.
- Replanejamento e chamada de provedores recuperam o objetivo do job; análise de outra pergunta não é reutilizada.
- Requisito explícito de valor retornado com relação de evidência correspondente.
- Trace opcional limitado, com referências SHA-256, seleção/cobrança/extração/descarte. Não exporta texto, URLs, credenciais ou consulta privada.
- Diagnóstico externo real Math.hypot antes/depois, com SQLite temporário e sem modelo/UI. Resultado candidato: zero evidências utilizáveis, apesar de consultas contextualizadas. **NO_GO**.
- Dois diagnósticos externos adicionais: Bosch zero evidências; Revolta da Vacina uma fonte lida. Sem gold factual independente.
- Trace ampliado: HTTP/status/bytes/tipo observados, redirects validados, candidatos não selecionados, requisitos/passagens e fechamento seguro após timeout/cancelamento.
- DEV Object.assign: 12 slots, dez corpos recebidos, cinco redirects, duas falhas de transporte, três fontes com passagens de sintaxe e sete rejeições ENTITY_MISMATCH. Quatro leituras repetiram URLs entre frentes; falta corrigir sem perder extração por faceta.
- Modelo gratuito real: redação produzida, revisão bloqueada por rate limit; nenhuma síntese aprovada, sem retry/fallback pago.
- Chrome autenticado isolado: cancelamento/SSE/reload, fonte real sem modelo, tabela/CSV/teclado/reduced motion/zoom e reconexão. Medidas sem overflow em 1280/390/320. Inspeção encontrou recorte na captura de 390; pendente reproduzir. Não é validação de pesquisa autônoma concluída.
- Código em `592edd2` e `1df28b3`; suíte final do código: **1672 passed, 4 skipped, 2 warnings**, 298,70 s. Baselines 34/34, 59/59 e 16/16. Evidências em `validation-summary.json`.

## Limitações e próximo passo exato

1. Reproduzir no corpus DEV a perda entre candidato, texto extraído e relevância. Não ajustar regras usando `ctx-01` como holdout: já foi examinado e passa a ser apenas diagnóstico.
2. Completar ranks/provedor/query→requisito, perdas até síntese e cobertura dos leitores que não usam `research.baixar`. O transporte do leitor HTML já está instrumentado; campos desconhecidos continuam null.
3. Propagar o contexto completo também nas reformulações internas do orquestrador. O lock estrito atual fica na fronteira do agente; pesquisas rápidas mantêm sua recuperação compacta compatível.
4. Validar aliases, seguimentos conversacionais, requisito novo em perguntas com restrições e consultas longas sem truncar condições. O fallback conservador pode reduzir diversidade.
5. Executar replay completo com candidatos/documentos/respostas congelados e os mesmos slots, depois novo conjunto externo independente. O conjunto externo atual foi congelado **após** a primeira implementação, não atende sozinho ao requisito de holdout pré-implementação.
6. Executar os seis E2Es completos A–F quando houver revisão gratuita disponível; diagnóstico atual bloqueado por rate limit. Completar galeria/exports/fluxos offline e reproduzir o recorte de 390. Cancelamento e fixture de entrega já foram testados no stack isolado.
7. Atualizar relatório, suíte e commits locais; manter NO_GO até evidência real consistente. Não fazer push/deploy.

Os arquivos anteriores V5.9.9.5 e benchmarks congelados permanecem inalterados.

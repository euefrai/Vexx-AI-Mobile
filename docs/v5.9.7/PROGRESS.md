# V5.9.7 — progresso

- HEAD local inicial `7beb67b6bc21b6d572449a149f3f254784cce64f`; remoto atualizado por fetch: `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`. Main correto, remoto sem commits exclusivos, cinco commits locais V5.9.6 pendentes. Artefatos não rastreados anteriores preservados.
- Baseline integral: 1.374 passed, 4 skipped (`qa-artifacts/v597/baseline.log`). Skills diff-code-writer/token-efficient mantidas; Playwright usado no Chrome real para componentes, sem alegar sessão autenticada do app.
- Prioridades: fontes originais e traces; conclusão/bloqueio recuperável; evidência científica limitada; estado JDUI por owner/job com proteção contra resposta atrasada; validação e gate condicional de publicação.
- Ledger: `research_agents.py:agente_analista` cobra slot de página por RSS que não abre; `executar` pode concluir com rate_limit e impedir retomada; `public/app.js:researchWorkspaceAbrir/researchCarregaView` sem contexto persistente nem guard contra resposta tardia; `docs_agent.py:_extrair_pdf` extrai até 200 páginas antes do corte feito pelo leitor de pesquisa.
- Não repetir ganhos concluídos. Sem serviços pagos, mudança de identidade/clima, motor paralelo ou reinício do PC Agent. Push apenas após GO/GO_WITH_LIMITATIONS e compatibilidade/deploy preparados.

## Implementado e verificado

- `4778d0b`: separação feed/leitura; prioridade de NewsArticle; traces; evidência vazia/não lida; conclusão parcial/bloqueada; retomada explícita; PDF limitado e seções por página.
- `79cae34`: contexto persistente por owner/job, guards contra respostas atrasadas, expansão estável e tabelas mobile; harnesses reproduzíveis.
- Final: 1.385 passed, 4 skipped, 2 avisos de depreciação, 180,76 s. Benchmarks 34/34, 59/59, 16/16. Quality Lab preservado.
- Chrome: estado IndexedDB preservado em reload e troca de pesquisa/dono; 320 px sem overflow da página; quatro contratos VM passaram. Não houve login do app no harness.
- Externo: 12 cenários de busca, só um com fonte lida aceita; zero resposta inteiramente confirmada. Um artigo original e dois PDFs parciais lidos em testes diretos separados. Modelo gratuito fez uma chamada e não aprovou a síntese.
- Segurança: scan por padrões em 241 arquivos de alterações/artefatos, zero ocorrência; sem valores de credenciais no relatório. Remoto após fetch ainda `ed3b9984b9054bfa97fc3c9f0831bf5b23e225e3`, 0 commits exclusivos remotos e 7 locais antes da documentação.
- Gate: GO_WITH_LIMITATIONS; publicação e observação registradas em RELEASE_DECISION. Sem migração de dados, mudança de autenticação, protocolo de mensagens, dependências ou configuração Render. Agente de produção preservado.
- Publicado `0814864e0e20bcb94f22a0b4fe861b205c15ed7c`; CI 40010107263 success; deploy automático observado, health e PC online. Código sem alterações pendentes; somente relatório/recibo pós-publicação atualizados localmente para evitar outro deploy documental. Próximo início normal do PC Agent é necessário para garantir carregamento integral dos módulos Python novos; o processo existente não foi reiniciado.

## Próximo passo funcional

Melhorar a descoberta de artigos originais para Ubatã e a pertinência de trechos científicos, usando os traces de rejeição desta rodada. Não ampliar a aceitação de região/data nem confundir leitura direta com descoberta completa. A pesquisa ainda não tem síntese científica real aprovada nesta avaliação.

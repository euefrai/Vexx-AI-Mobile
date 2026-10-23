# Vexx AI — diagnóstico de disponibilidade da pesquisa

Base `4f90d75`. Evolução pequena da síntese/revisão, sem trocar modelos, credenciais, permissões ou bancos reais. Push das alterações estáveis autorizado nesta etapa.

## Encontrado e corrigido

1. O revisor convertia qualquer exceção em “indisponível”, perdendo o código original. O avaliador também não reconhecia códigos reais do cliente, como `vazia`, `formato`, `indisponivel` e `protocolo_ferramenta`. Agora há um vocabulário compartilhado e fechado: causa da revisão (provedor, orçamento, cancelamento ou resposta tardia) e código permitido ficam no resultado/evento. Mensagem, detalhe HTTP, URL, corpo privado e chave não são persistidos.
2. O cliente síncrono agrupava timeout e falha de conexão no mesmo código. Timeout direto ou encapsulado em `URLError` agora recebe `timeout`; falha de conexão continua `indisponivel`. Não houve alteração de retries, circuit breaker ou configuração do provedor.
3. Foi reproduzida uma resposta `PARTIAL` com `quote`/`claim` literais no nível superior. Antes, a candidata era descartada por formato. Essa única variação conhecida agora é normalizada **somente para PARTIAL/INCONCLUSIVE**, após conferir tamanhos, claim no parágrafo e quote em fonte citada. Os campos auxiliares são descartados depois da validação. Não se recupera `SUPPORTED`, não se corrige estado desconhecido e não se aceita campo arbitrário.

## Validação

- Baseline focado: **102 passed**.
- Focados finais: **126 passed**, incluindo 24 testes novos de diagnóstico, erro sem segredos, orçamento/cancelamento, timeout/conexão e limites da normalização. Assertions anteriores preservadas.
- Suíte completa final: **1.270 passed, 4 skipped, 2 warnings em 340,55 s**. Verificação de sintaxe, whitespace e credenciais feita antes do commit.
- Doze chamadas reais ao modelo configurado, sobre casos sintéticos congelados: **nenhuma indisponibilidade nesta execução**. Dez revisões tinham formato válido; duas foram recusadas. Portanto, não se afirma que a causa das indisponibilidades históricas foi reproduzida ou eliminada.
- Uma recusa veio da variação literal descrita acima; a outra veio de um estado desconhecido (`CONTRADIICTED`), que continua recusado. Replay das mesmas respostas salvas, **zero inferências novas**: formato válido **10/12 → 11/12**, concordância de estado **8/12 → 9/12**. Isso mede tratamento de formato nesse replay, não melhoria semântica universal ou disponibilidade futura.
- Nenhuma resposta sem suporte foi promovida a `SUPPORTED` pela normalização. Persistência, isolamento, relatórios e fluxos antigos continuam cobertos pelos testes.

Evidências: `qa-artifacts/research-availability-{baseline,focused,full-suite}.log`, `research-availability-diagnostic*.json` e `research-availability-replay.json`. As duas sondas dividem os 12 casos e não executam retries. O modelo segue `poolside/laguna-s-2.1:free`.

## Publicação

Git remoto verificado sem divergência antes da publicação. Três commits anteriores de síntese/revisão/calibração estavam pendentes. O push incluirá esses commits e esta correção, após a suíte completa e inspeção do diff.

Validação local concluída, incluindo `node --check public/app.js`. Este commit de entrega será enviado à main com os três anteriores. O resultado do push e do CI pós-push é informado na resposta de entrega; os testes locais não são apresentados como CI remoto.

Sem reinício do PC Agent ou teste pela interface de produção nesta etapa. Render pode implantar automaticamente o backend após o push, mas os módulos do PC só passam a rodar no processo ativo após seu próximo reinício normal. Não se apresenta a execução CLI como smoke de produção.

## Limites

O revisor ainda pode errar classificação, contexto e significado. A resposta malformada ou sem revisão válida mantém o fallback. A nova instrumentação permite diagnosticar a próxima ocorrência real; não garante disponibilidade do serviço. Falhas históricas sem código original continuam sem causa comprovada. Nenhum plano/provedor foi ativado ou cobrança alterada.

Arquivos de produção: `research_synthesis.py`, `research_agents.py`, `hermes_bridge.py`. QA: `tests/test_research_availability.py`, `tools/evaluate_semantic_support.py`, evidências e este relatório. Sem dependências ou migrações novas.

# Júlia Mobile — Arquitetura (4.0)

## Componentes reais (verificados no código)

```
Celular/PWA ──HTTPS/WSS──▶ Render (FastAPI, SEM banco)
  IndexedDB: messages, sessions, ui_state, meta          │  Auth Argon2id + cookie
  Streaming SSE + rAF                                    │  HttpOnly + CSRF + Origin
                                                         ▼
                                              Agente Python (1 pareado)
                                                         │  SQLite WAL (fonte definitiva)
                                                         ▼  Hermes Proxy loopback → Laguna S 2.1
```

## Identidade e isolamento (V4.0)

- Sessão carrega `user` (dono). Relay repassa `owner` em todo RPC ao agente.
- Toda tabela de dados tem `owner_id TEXT DEFAULT 'local'`:
  `messages`, `ai_requests`, `memories`, `memory_facts`, `documents`,
  `doc_chunks`, `ui_state`. Migração idempotente (`ADD COLUMN` + índice).
- **Toda query do agente filtra por `owner`**; todo handler valida ownership.
  Teste de isolamento: usuário B não lê/nem apaga nada de A (cobertura em pytest).
- Conta única hoje (`JULIA_USERNAME`); cadastro multi-conta é V4.6. A fundação
  (colunas + enforcement + testes) entra na V4.0 sem mudar comportamento local.

## Contexto e grounding

Montagem por prioridade com orçamento de caracteres (~12k no histórico):
`system` → fatos confirmados e falas do usuário recuperadas por relevância →
trechos de docs → pesquisa (rotulada com data) → histórico da conversa atual
(fences viram `[interface]`). A busca histórica percorre mensagens anteriores
do mesmo dono; fala antiga só entra no prompt quando compartilha termos com o
pedido. Não há fallback para fatos sem relação.
Respostas de ferramenta vão rotuladas (`RESULTADO DE PESQUISA EM ...`);
regra explícita: admitir desconhecimento, nunca inventar links/datas/preços.

O SQLite mantém o histórico completo já sincronizado, mas o aprendizado de fatos
é seletivo: informações sensíveis e datas ambíguas esperam confirmação. Tabelas,
cartões e checklists são renderizados pelo catálogo JDUI validado, não por código
executável gerado pelo modelo.

## Offline-first (preservado)

IndexedDB é escrita primeira; sync idempotente (`INSERT OR IGNORE` + ACK);
tombstones para exclusão; `ui_state` com merge newer-wins. PC desligado =
leitura/escrita local + IA indisponível (mensagem clara, sem simulação).

## Histórico, materiais e contexto do aparelho

- A busca rápida do painel percorre mensagens locais do dono ativo; mensagens
  antigas ainda não sincronizadas com o PC não aparecem na busca do agente.
- Respostas salvas e estados de tabelas, formulários, calculadoras e checklists
  ficam no IndexedDB deste aparelho e são removidos ao apagar o cache.
- Exportações em Markdown, JSON, TXT e CSV são geradas no aparelho; o XLSX é
  montado pelo relay autenticado com no máximo 500 mensagens, sem armazenar a
  planilha. PDF usa a janela de impressão do navegador (Salvar como PDF).
- Cada pedido envia a hora local em ISO 8601 e o fuso IANA do dispositivo.
  Cidade e coordenadas aproximadas (arredondadas a duas casas) só são incluídas
  quando o usuário ativa o recurso e pergunta sobre um lugar. Não há geolocalização
  contínua nem obtenção automática em segundo plano.

## Limites assumidos

- 1 PC pareado, 1 agente WS por vez; sem fila de tarefas (V4.5).
- Render Free hiberna; sem banco na nuvem; sem push/notificação com app
  fechado (impossível sem infra persistente — documentado, não prometido).
- Embeddings vetoriais: NÃO adotados (sem benefício mensurável p/ escala atual;
  FTS5 só se a busca local exigir — hoje `LIKE`/índices bastam).

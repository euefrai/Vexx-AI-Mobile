# RELATÓRIO JÚLIA 4.0 — Fundação

Data: 2026-10-13. Sem push, sem deploy (regra). `pytest -k "not e2e"`: **77 passed**.

## Implementado (FUNCIONAL)
- **Multiusuário (fundação)**: `owner_id` em messages/ai_requests/memories/
  memory_facts/documents/doc_chunks/ui_state; migração preserva dados
  (verificado em banco antigo real); `dono_valido()` sanitiza; todo handler e
  todo RPC filtra por dono; `k` de ui_state com guarda anti-colisão.
- **Chat profissional**: arquivar (filtro 📦), fixar (📌 primeiro), exportar
  .md/.json local, regenerar (`ai_reset` + nova inferência), continuar
  (`ai_continue`, anexa ao mesmo reply_id), busca no histórico (títulos+texto),
  renomear/copiar/interromper (já existiam).
- **Contexto**: orçamento 12k chars (recentes primeiro), fences fora do
  histórico, REGRAS_CONFIANCA em todo system, fontes rotuladas com data.
- **Avaliação conversacional**: T1–T8 automatizados e passando.

## Parcial / ausente (declarado, não simulado)
- Cadastro multi-conta: AUSENTE (fundação pronta; é V4.6). Conta única ativa.
- Fórmulas KaTeX, edição in-place, ramificação, share-link: AUSENTES (ROADMAP).
- screen/input seguem nível-dispositivo (dono do PC), sem per-user: PARCIAL.
- Embeddings: AUSENTE por decisão (sem benefício mensurável; busca é lexical).
- E2E com processos reais: não rodado neste ciclo (lento); unit+relay cobrem.

## Arquivos
Criados: docs/{ARCHITECTURE,ROADMAP,PROGRESS}, tests/{test_isolamento,
test_chatpro,test_avaliacao}, RELATORIO_fajulto_4.0.md.
Modificados: pc_agent.py (owner end-to-end, reset/continue, orçamento,
grounding), server.py (owner em 14 RPCs, 2 endpoints), docs_agent.py (owner),
public/{app.js,index.html,styles.css} (arquivo/fix/export/busca/regen/continue).

## Próximos (V4.1)
Memória tipada com autorização e proveniência; temporais sem ano inventado;
testes de contradição.

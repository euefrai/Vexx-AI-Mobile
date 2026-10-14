# RELATÓRIO JÚLIA 4.1 — Memory Intelligence

Data: 2026-10-13. Sem push, sem deploy. `pytest -k "not e2e"`: **86 passed**.

## Implementado (FUNCIONAL)
- **Estruturada**: tipos (semantica/temporal/episodica/trabalho), assunto,
  status (confirmada/pendente/contraditória via histórico/arquivada),
  origem_conv/msg, valido_ate; `memory_events` (titulo/data_iso/assunto/status);
  `memory_settings` (toggle); FTS5 com fallback.
- **Extração**: candidatos tipados; sensível e data ambígua → proposta +
  pergunta de confirmação; explícito passa mesmo pausado; datas PT-BR
  (ano explícito/relativo resolve; sem ano pergunta, nunca presume).
- **Proveniência**: origem + data no prompt ("guardado em 12/10"); eventos com
  "faltam N dias"; pendentes viram nudge ("não afirme que guardou").
- **Recuperação**: híbrida FTS+overlap+recência, só confirmadas, no orçamento.
- **Atualização/contradição**: upsert + antiga em `memory_facts`; correção vence.
- **Painel**: busca local, badges de tipo, corrigir (PUT), pendentes
  confirmar/descartar, toggle aprendizado, eventos. Tudo com owner enforced.
- **Isolamento**: pendentes/eventos/settings por dono; teste multiusuário.

## Parcial
- Confirmação entende frases explícitas, não "sim" solto (decisão anti-ambiguidade).
- LLM de fundo classifica tipo/confiança; sensível ou conf<0.6 → proposta.
- Pessoas: padrão "X é meu/minha Y"; casos complexos ficam para V4.2+.

## Ausente (declarado)
- Cadastro multi-conta (V4.6); revisão espaçada e flashcards (V4.2);
  E2E real neste ciclo.

## Arquivos
Modificados: pc_agent.py (núcleo V4.1), server.py (6 endpoints),
public/{app.js,index.html,styles.css} (painel), docs/JULIA_MOBILE_PROGRESS.md.
Criados: tests/test_memoria41.py (9), RELATORIO_JULIA_4.1.md.

## Próximo (V4.2)
Learning Engine sobre esta base: planos, flashcards, simulados, desempenho.

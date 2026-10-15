# JÚLIA Inference Reliability (V4.3.1)

## Diagnóstico Hermes (16/10/2026, re-sondado hoje)

| Item | Resultado |
|---|---|
| `GET /v1/models` | OK — 423 modelos em ~1 s |
| `laguna-s-2.1:free` (preferencial configurado) | `BridgeErro(vazia)` em ~2,4 s — HTTP 200 com corpo sem conteúdo |
| Outros slugs (`lfm-2.5`, `ling-3.1`, `gemini-nano`) | `BridgeErro(modelo-nao-encontrado)` — proxy rejeita o slug |
| Classificação | Falha de **provedor**, não de configuração (modelo é o padrão do `.env`) nem de código (bridge classifica corretamente) |

## Mecanismos implementados

- **Códigos**: `quota` (402), `pedido` (422), além de `auth`, `modelo-nao-encontrado`,
  `rate_limit`, `provedor`, `timeout`, `vazia`, `todos_falharam`, `circuito_aberto`.
- **`tentar_modelos`**: `[preferencial, *fallbacks]` (máx 5); para em `auth`;
  backoff 1/2/4 s; com 1 modelo o erro original passa transparente (sem reembalar);
  `model_usado` + `tentativas[]` no retorno para auditoria.
- **`chat_stream_fb`**: troca de modelo só antes do 1º delta; depois, propaga.
- **Circuit breaker** por base: 4 falhas → 120 s aberto (bug de contagem zerada
  achado e corrigido por teste).
- **Config**: `JULIA_AI_MODEL` + `JULIA_AI_FALLBACKS` (máx 4 slugs validados).
- Chamadas LLM são só leitura: repetir em fallback **não** duplica ação externa;
  `reply_id` único preserva idempotência.
- `ai_completa`, `ai_continuar`, `ai_stream_worker` e todas as sínteses
  (prova/aula/JDUI/memória) usam o caminho com fallback e registram o modelo real.

## Streaming confiável (verificado ponta a ponta)

Bridge (`vazia`/`parcial`/`cancelada`/`timeout`) → agente (`ai_error`/
`ai_cancelled`, nunca `ai_done` vazio) → relay SSE → app (erro vira exceção +
`Tentar novamente`; stream vazio tenta `/api/ai` completo 1× e só então
falha com "Resposta vazia da IA"). Sucesso vazio é impossível por construção.

## Limites conhecidos

- Sem modelo funcional no provedor hoje: fallback não cria capacidade, só
  resiliência. Erro final é compreensível (`_conselho_final` por código).
- E2E usa Hermes falso; inferência real: BLOQUEADA no provedor, quota zero.

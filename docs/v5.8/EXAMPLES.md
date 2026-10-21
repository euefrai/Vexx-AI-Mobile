# Examples — real contracts

The examples below are valid V5.8 shapes. They are illustrative payloads; a
running system must populate them from real persisted records. Invalid or
empty blocks are omitted with a textual note, never returned as raw JSON.

## `researchplan`

```json
{
  "type": "ui",
  "component": "researchplan",
  "props": {
    "title": "Plano de pesquisa",
    "objective": "A dose de 400 mg de café é segura para adultos?",
    "mode": "profunda",
    "status": "running",
    "steps": [
      {"id": "p1", "title": "Buscar diretrizes de cafeína", "kind": "busca",
       "status": "done", "detail": "frente primária",
       "stop_condition": "3 fontes lidas ou orçamento esgotado",
       "dependencies": []},
      {"id": "p2", "title": "Ler ensaios clínicos", "kind": "ler",
       "status": "running", "dependencies": ["p1"]}
    ],
    "budgets": {"buscas": 8, "paginas": 12, "midia": 16, "replans": 2},
    "used": {"buscas": 2, "paginas": 1, "replans": 0},
    "sources": [{"id": "plan", "title": "research_agents.montar_plano",
                 "kind": "backend"}]
  }
}
```

The backend recomputes `done/total/percent`; any client/model-supplied percent
is ignored. Step statuses are normalized to `todo`, `doing`, `done`, `error`,
`skipped`, `paused`.

## `evidence`

```json
{
  "type": "ui",
  "component": "evidence",
  "props": {
    "title": "Evidências por afirmação",
    "claims": [{
      "statement": "O café é seguro em doses de até 400 mg por dia em adultos saudáveis.",
      "state": "SUPPORTED",
      "method": "verificação lexical determinística",
      "coverage": 0.91,
      "sources": [{
        "id": "ev-1",
        "title": "Ensaio clínico sobre cafeína",
        "url": "https://example.com/estudo",
        "domain": "example.com",
        "date": "2026-09-01",
        "relation": "SUPPORTS",
        "read": true,
        "access_state": "read",
        "used_excerpt": "Até 400 mg/dia não houve eventos graves."
      }]
    }]
  }
}
```

Counts (`found_count`, `read_count`, `used_count`, `supporting_count`,
`contradicting_count`) are derived server-side from the attached sources. A
`SUPPORTED` claim with no real source is invalid and is omitted.

## `media`

```json
{
  "type": "ui",
  "component": "media",
  "props": {
    "title": "Mídia descoberta (não é evidência)",
    "items": [{
      "type": "image",
      "title": "Ensaio clínico",
      "url": "https://example.com/grafico-cafe.png",
      "source_url": "https://example.com/materia-cafe",
      "publisher": "example.com",
      "date": "2026-09-01",
      "rights": "não informado",
      "access_state": "metadata_only",
      "validation_state": "unverified",
      "analysis_state": "not_analyzed",
      "evidence": false
    }]
  }
}
```

Even if a payload sends `analysis_state: "visually_analyzed"` or
`evidence: true`, the validators force `not_analyzed` and `false`.

## `filecard`

```json
{
  "type": "ui",
  "component": "filecard",
  "props": {
    "title": "Exportar pesquisa",
    "files": [
      {"name": "Relatório", "url": "/api/research/export?job_id=rj-abc&formato=md",
       "kind": "md", "status": "generated", "source": "Vexx AI"},
      {"name": "Dados", "url": "/api/research/export?job_id=rj-abc&formato=csv",
       "kind": "csv", "status": "generated", "source": "Vexx AI"}
    ]
  }
}
```

Allowed URLs are remote `http(s)` URLs or the narrow same-origin
`/api/research/export?job_id=…&formato=md|csv|json`. Any other relative path
(`/api/admin`, etc.) is invalid.

## Export request

```text
GET /api/research/export?job_id=rj-abc&formato=md
Cookie: JULIA_session=…
```

Response:

```text
HTTP/1.1 200 OK
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="vexx-pesquisa-rj-abc.md"
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

The relay resolves the authenticated owner, asks the PC agent for status,
evidence and hypotheses, and renders bounded bytes in memory. The pure renderer
never queries SQLite.

## Useful commands

```powershell
# focused V5.8 contract tests
python -m pytest tests/test_v58_deep_research.py tests/test_jdui.py tests/test_frontend_smoke.py -q

# full local suite
python -m pytest -q

# frozen research benchmark (fixtures)
python tools/bench_pesquisa_v57.py --sem-salvar

# performance of the new pure modules
python tools/bench_v58.py

# real Chrome desktop + emulated mobile, isolated stack
python tools/chrome_e2e_v58.py

# JS syntax
node --check public/jdui.js
node --check public/app.js
```

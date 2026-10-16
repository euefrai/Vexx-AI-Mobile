# JÚLIA Research Benchmarks (V4.9)

## v1 (`research_quality_v1.json`)

11 documentos txt/csv/html, 8 casos (factual_qa, multi_hop, contradiction,
attribution, document, numerical, temporal, adversarial), cenários de
checkpoint 10/25/50. Digest fixado em teste.

## v2 (`research_quality_v2.json`)

+JSON doc, abstracts acadêmicos (original × reprint para atribuição),
par temporal 2023/2025, injeção adversarial, documento longo (truncamento),
numérico com unidades, multi-hop, `factual_pairs` (6 pares rotulados),
`memory_cases` + `memory_facts`, `graph_cases` + `graph_evidence`.

## Casos por categoria (§3)

Factuais, multi-etapa, evidências distribuídas (multi-hop), contraditórias,
republicações, falsas, longas (truncamento verificado), interrupção/
retomada, prompt injection, multiusuário, numéricas com unidades,
desatualizadas (latest_source), acadêmicas (abstract_only sinalizado),
formatos (PDF/DOCX/XLSX/HTML/JSON/CSV/MD/TXT gerados em runtime).

Critérios objetivos nos asserts; documentos congelados; sem rede (exceto
sondas manuais documentadas e E2E DDG).

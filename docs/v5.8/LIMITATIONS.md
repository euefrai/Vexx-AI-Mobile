# V5.8 limitations

These limitations are part of the result, not footnotes to hide.

## Research and evidence

1. **No LLM inference was exercised in V5.8.** Hermes/model availability is
   variable. Planning, verification and synthesis are deterministic/extractive;
   `llm=false` is recorded. Semantic entailment and semantic diagnosis remain
   BLOCKED.
2. **Claim verification is mostly lexical.** `SUPPORTED` means the stored
   excerpt/coverage supports the statement under the deterministic method; it
   is not causal proof or expert review.
3. **External providers are variable.** 403, 429 and bot walls are recorded as
   BLOCKED. There is no bypass. A provider failure is never converted to a
   positive result.
4. **Open-web quality is not continuously measured.** Frozen fixtures prove
   regression behavior, not today's web.
5. **Replanning is bounded** by mode budget (0–3 rounds) and stops on timeout,
   budget or no gaps. It can miss evidence outside its queries.
6. **Concurrency is not implemented.** The configured concurrency value is a
   ceiling; execution is sequential. No speedup is claimed.
7. **Resume is step-level.** It restores persisted jobs/checkpoints, not an
   in-flight HTTP page read.

## Media

8. Media is **discovery only**: type, URL, source page, publisher/date/rights
   when present, access/validation state, excerpt. No bytes are downloaded,
   rehosted, thumbnailed server-side, transcribed or visually analyzed.
9. “Imagem indisponível” is the expected fallback for bad/expired remote URLs.
10. Video discovery is not video understanding. No transcript or watched-content
    claim is made.
11. Rights are often “não informado”; the UI does not grant reuse rights.

## JDUI and workspace

12. JDUI rendering is validated native components, not arbitrary HTML/JS. An
    invalid block is omitted with a textual note; it is not repaired into
    something the model did not provide.
13. The “Pesquisas” page is a saved-job viewer with exports, not a full notebook
    with annotations, report version history or collaborative editing.
14. Charts/ECharts, PDF.js, Video.js and Docling were evaluated but not added.
    The deep-research view does not add a new interactive chart/PDF/video
    analyzer.
15. Only MD/CSV/JSON exports exist; no PDF/DOCX export, scheduling or persistent
    export storage.

## Testing and environment

16. Chrome E2E uses headless Chrome 155 on a local isolated stack. Mobile is
    **emulated** 390×844; no physical device was tested.
17. The Chrome job is locally pre-persisted to exercise the real UI/route path;
    it is not a live external investigation.
18. Reload during a live model stream was not re-run in Chrome. SSE replay and
    idempotence are covered by tests; the browser-level case remains partial.
19. No production/Render validation was performed. PID `24356` and production
    data were untouched.
20. 4 tests are skipped; they are not counted as passes. The semantic/LLM
    benchmark is intentionally blocked.
21. The local suite includes a concurrent audit snapshot; the 929→954 delta is
    not exclusively V5.8.
22. Performance measurements are for pure Python modules on Windows; they are
    not production concurrency or browser-render numbers.

## Scope

23. No push, deploy, credential change, paid service, Lucas identity change, 3D
    engine change, Júlia extension change, Fajulto Studio change, social
    integration or Apify.
24. No security control (SSRF, CSP, RBAC, owner isolation) was weakened.
25. The working tree contains preserved concurrent audit artifacts; V5.8 did not
    delete or rewrite them.

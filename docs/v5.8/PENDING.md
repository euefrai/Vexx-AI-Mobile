# Pending work after V5.8

Ordered by risk and dependency. None of these is claimed as done.

## Requires explicit authorization

1. **Push/deploy V5.8** and validate the published stack. Production PID
   `24356` must not be restarted without approval.
2. **Run real external E2E** against live providers from the published or
   authorized environment, recording BLOCKED/PASS separately.
3. **Exercise Hermes with a real model** (429/quota/stream/cancel) and compare
   semantic synthesis quality. Do not enable a paid service without approval.
4. **Physical mobile device validation**; the current mobile evidence is
   emulated.

## P1 — correctness and evidence

5. Browser-level reload during a live streaming response, including cursor,
   replay, duplicate suppression and terminal flush.
6. Real media download/thumbnail/transcript pipeline with rights, byte limits,
   SSRF checks, owner isolation and an explicit “analyzed” state backed by real
   bytes. Until then keep `not_analyzed`.
7. Real PDF layout/OCR evaluation (PDF.js viewer vs Docling) with measured RAM
   and CSP impact; do not adopt on Render Free by default.
8. Semantic claim verification when a real model is available, preserving the
   five states and never converting BLOCKED to PASS.
9. Actual bounded parallelism (if desired) for page/agent work, with the
   configured concurrency ceiling and deterministic ordering.

## P2 — product completeness

10. Richer research workspace: notes, report versions, saved view state,
    comparison of runs, and explicit owner-scoped retention.
11. PDF/DOCX export and optional chart rendering, with real data and textual
    fallbacks.
12. Accessibility audit with a real tool (labels, focus order, contrast,
    screen-reader reading of progress/evidence); current checks cover keyboard
    buttons, ARIA progress and overflow, not a full WCAG audit.
13. Live news/commercial quality cases with source dates and provider
    variability; no benchmark inflation.
14. Review provider metrics/observability for production; current metrics are
    diagnostic.

## Housekeeping

15. Address remaining untracked audit/QA artifacts intentionally; V5.8 preserved
    them but did not decide their final repository layout.
16. Decide whether the V5.8 Chrome/benchmark tools should run in CI and where
    Chrome is available.
17. Keep the capability matrix and limitations synchronized with any future
    deployment evidence.

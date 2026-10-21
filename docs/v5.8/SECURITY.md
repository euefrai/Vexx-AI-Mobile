# Security boundaries — V5.8

## Authentication and ownership

- `/api/research/jobs`, `/evidence`, `/status`, `/view` and `/export` call
  `verify_session` and resolve the owner through the existing revocation/session
  path before contacting the PC agent.
- The relay request includes the authenticated `owner`; the agent queries
  `owner_id` in SQLite. There is no client-supplied owner parameter.
- `research_view` and `research_exports` are pure and DB-free; the server passes
  only the authenticated owner's relay records.
- Tests: `test_relay_view_and_export_routes_return_real_validated_bytes`,
  `tests/test_isolamento.py`, owner-scoped hypothesis/report/store tests.

## Export safety

- Format allowlist: `md`, `csv`, `json` only.
- Bounded output: 2,000,000 bytes, 200 items.
- CSV cells are neutralized against spreadsheet formula injection (`=`, `+`,
  `-`, `@` and leading control characters) by `_csv_cell`.
- Filename is sanitized; `Content-Disposition: attachment`.
- `Content-Type` is explicit and `X-Content-Type-Options: nosniff`;
  `Cache-Control: no-store`.
- No export file is persisted on Render; bytes are rendered per request.
- Remote media is never proxied or rehosted.

## JDUI safety

- Version allowlist `JULIA-ui-message/v1`.
- Component/property allowlists; unknown blocks are dropped.
- No model-supplied HTML or JavaScript is executed.
- `filecard` accepts remote `http(s)` URLs or the narrow same-origin
  `/api/research/export?job_id=…&formato=md|csv|json`; other local paths are
  rejected.
- `media` cannot be evidence and `analysis_state` is forced to `not_analyzed`.
- `evidence` rejects a supported claim without a real source.
- Plan progress is recomputed; a spoofed `percent` is ignored.
- Limits: 6–8 blocks, 24 plan steps, 10 claims, 12 sources/claim, 12 media,
  8 files.
- Node parity harness covers the new frontend validators (including the
  file-card allowlist and media non-evidence rule).

## SSRF and acquisition

- Media discovery consumes HTML already obtained by the existing safe
  acquisition path; it does not fetch arbitrary media URLs.
- Only `http(s)` media URLs are kept; credentials are rejected.
- The existing SSRF/DNS/redirect protections in `research.py`/`providers.py`
  are unchanged. Tests include `test_proxy_url_bloqueia_ssrf` and provider
  block/redirect suites.
- 403/429/bot-wall remain `BLOCKED`; there is no CAPTCHA bypass, proxy rotation
  or paid unblocking.

## CSP and browser

- No new external script, style, font or media origin was added by V5.8.
- Media `<img>`/`<video>` use remote URLs and lazy loading; failures show a
  textual fallback.
- The Chrome E2E recorded no uncaught exceptions. It ignored the expected
  pre-login `/api/session` 401 only.
- Heavy libraries were not added, so no new `script-src`, `worker-src` or
  `media-src` allowance is required.

## What was not changed

- Credentials, paid services, RBAC, SSRF policy, CSP policy, multi-user
  isolation, 3D engine, Júlia extension, Fajulto Studio, social/Apify.
- Production PID `24356` was not stopped or restarted.
- No push or deploy was performed.

## Residual risks

- Exports depend on the relay returning owner-scoped data; a bug in the PC
  agent's owner filter would be serious. The route and agent tests cover the
  normal path, not every production migration.
- Remote media URLs are third-party content; availability, rights and safety
  are not guaranteed. The UI labels them as discovered, not evidence.
- A future real media/PDF viewer would enlarge the CSP and memory surface and
  must be threat-modeled before adoption.

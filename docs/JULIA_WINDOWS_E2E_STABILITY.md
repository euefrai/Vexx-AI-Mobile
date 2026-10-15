# Windows E2E lifecycle and stability

## Harness changes

The real-process tests previously passed writable log files directly as
`stdout` to child processes. On Windows the child inherits that file handle;
temporary-directory cleanup can then receive `PermissionError` even after
the parent closes its own handle. The tests now pipe child output to a reader
thread owned by the pytest process and write diagnostics locally. This keeps
the temporary log handle out of the child process.

`LoggedProcess` owns the child lifecycle: terminate, bounded wait, kill on
timeout, bounded wait again, join the output reader and explicitly close the
parent-owned log. Teardown failures are raised, not converted into success.
The E2E tests use pytest's per-test `tmp_path`, so logs remain available after
failures. Relay ports are allocated per run rather than hard-coded.

The research E2E now waits for both a terminal job status and the terminal
`research_completed` event; these are persisted separately and may become
visible on adjacent polls. Fake server threads are joined explicitly.

## Validation status

The process-helper and both real-process E2Es passed together in the final
focused run. Three consecutive repository-suite runs each passed 312 tests
with two skips and three warnings, excluding one unrelated test that fails
against an uncommitted `public/jdui.js` edit. The same test passed against the
committed `HEAD` version. See `RELATORIO_JULIA_4.9.md` for durations and the
warning details. This is not represented as three unqualified full-suite
passes.

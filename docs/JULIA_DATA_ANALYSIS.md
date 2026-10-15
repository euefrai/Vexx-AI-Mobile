# Julia Structured Data Analysis

## Scope

`structured_analysis.py` performs bounded deterministic operations on supplied
CSV, JSON, and tabular rows. It does not ask the model to calculate values and
does not invent missing observations. It preserves source and caller-supplied
period, units, and methodology in each result's `provenance`.

The service supports column validation, filtering, sorting, grouping, means,
differences, proportions, IQR-based outlier identification, and chart-series
preparation. Unit conversion reuses `units.py`; incompatible unit groups are
marked and are not subtracted or aggregated as though compatible.

## Resource limits

Inputs are bounded to 5 MiB, 10,000 rows, 100,000 cells, 5,000 columns, and
64 KiB per cell. Invalid columns, malformed data, unsupported operations, and
limit violations raise `AnalysisError`; they are not converted into empty
success-shaped results.

## JDUI output

`research_visualizations.py` adapts chart-series and difference results into
the existing `chart` and `compare` JDUI components. It rejects incompatible
units, non-finite values, unaligned x-axes, and data beyond the component's
bounds. Source ID/title and any supplied URL or row locator are preserved in
the component's validated `sources` field. The `melhor` comparison marker is
left blank because numerical difference alone cannot determine which result
is preferable. Where supplied, period and data methodology are carried into
the rendered provenance alongside the analysis operation and unit.

JDUI renders provenance references as text or safe HTTP(S) links. It does not
generate a chart from a prompt without a structured data result.

## Research chat integration

The explicit `analisar tabular chart` command requires `job`, `doc`, `x`, `y`,
and `unit`; `analisar tabular compare` requires `job`, `doc`, `group`, `value`,
`baseline`, and `unit`. `unit` must name a unit column or be explicitly set to
`none`. The document must be owned by the same user and conversation as the
research job. Its saved CSV/TSV/JSON original must exist and match the stored
size and extracted-content hash; truncated or changed originals are rejected.
JSON must use the tabular shape accepted by `structured_analysis.load_json`.
Only successful deterministic results are persisted in the job/checkpoint and
included as cited observations in reports. Ambiguous or incompatible inputs
produce a limitation instead of a chart.

## Validation and limits

Focused tests cover numeric operations, input bounds, units and provenance.
The JDUI adapter is tested against actual deterministic results from a small
CSV fixture. Statistical validity, source reliability, and comparability of
different methodologies remain contextual questions; calculated values are
not a truth score.

A local synthetic pipeline that constructed and grouped 10,000 rows into 10
categories completed in 576.20 ms with 4.24 MiB peak traced Python allocations
on the selected Windows/Python 3.14 development environment. Input construction
was included in the measurement. This is a microbenchmark, not a production or
target-PC performance guarantee; `tracemalloc` does not capture all native
allocations.

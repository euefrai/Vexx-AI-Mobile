# Julia Document Intelligence

## Current capabilities

The document pipeline accepts PDF, DOCX, TXT, Markdown, CSV, TSV, XLSX, HTML,
and JSON. Existing extraction limits remain in force: uploads are bounded to
15 MiB, extracted text to 200,000 characters, PDF extraction to 200 pages,
and spreadsheet/table extraction is bounded by sheet, row, and column caps.
These limits protect the local PC agent from unbounded work.

Extraction now records document title, section and page/location hints, and
table hints where the parser can identify them. Text chunks retain a document
reference, owner, section/location, content hash, and index version. JSON is
parsed as data; embedded content is not executed. HTML scripts/styles are
removed by the existing extractor. DOCX macros, scripts, and other active
content are not run.

PDF extraction is text extraction only. Image-only or scanned pages do not
receive OCR, and the system must report that limitation rather than imply that
the page was read.

## Sources and ownership

Uploaded originals remain in the PC-owned document store. Document listing,
retrieval, summaries, topics, comparisons, deletion, and index operations are
owner-scoped. The authenticated server supplies the owner; client-provided
owner IDs are not authoritative. Deleting a document removes its stored
original and associated chunk/index records for that owner.

## Research behavior

The existing retrieval path can use SQLite FTS5 when available and falls back
to lexical retrieval. Cross-document comparison reports what was found and
distinguishes literal evidence of absence from content that was simply not
located. Search failure is not proof that a concept is absent. No embedding
provider, OCR engine, or semantic inference is required or claimed.

## Validation

Focused tests cover supported formats, JSON, extraction bounds, provenance,
retrieval, comparison, deletion, and ownership. Frontend smoke tests cover the
document-picker flow. OCR and semantic comparison remain unavailable without
the corresponding real capability.

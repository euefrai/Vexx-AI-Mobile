# Julia Document Retrieval

## Index and chunks

Document chunks are generated around paragraphs and section boundaries when
available instead of blindly cutting every fixed number of characters. Each
chunk retains its stable chunk/document IDs, owner, section or location, text
hash, index version, and reference to the uploaded source. Page numbers are
included only when the PDF parser provides them.

SQLite FTS5 supplies the text index when supported by the SQLite build. A
bounded lexical fallback remains available if FTS5 cannot be created. Both
paths retain owner filtering; there is no mandatory vector database or paid
embedding service.

## Retrieval and multi-document comparison

Retrieval returns the matching text plus provenance so answers and visual
components can cite the original file and location. The existing limits on
chunk count and snippet length continue to bound context sent to inference.
Whole-document context is not substituted for retrieval when only fragments
are needed.

Comparison across documents separates:

- Located evidence and its source locations.
- A literal absence statement only when the inspected content supports it.
- “Not located” or insufficient coverage when text search did not establish
  absence.

Lexical matching is not semantic proof. A match may require review, and failure
to find a term cannot establish that a concept is absent.

## Maintenance

Index-version metadata lets migrations rebuild chunk indexes without dropping
legacy document records. Owner-scoped deletion removes the selected original,
chunks, and FTS entries. No public/shared document URLs are created.

## Validation

Focused tests cover chunk boundaries, index creation/fallback, source
provenance, retrieval, cross-document comparison, legacy migration, and
owner-isolated deletion. Semantic retrieval and OCR are not claimed.

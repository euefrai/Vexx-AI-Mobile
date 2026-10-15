# Julia Academic Research

## Status and activation

Academic lookup is an optional capability in the existing research
orchestrator; it does not add another agent role. Enable it with
`JULIA_ACADEMIC_RESEARCH=1`. `JULIA_RESEARCH_MAILTO` is optional and is used
for polite Crossref requests. No API key, paid account, or automatic account
creation is required.

## Providers and access policy

- OpenAlex Works: keyless, bounded metadata searches with small page sizes,
  selected fields, request timeouts, and provider rate-limit handling. OpenAlex
  documents keyless use and per-second limits in its
  [official authentication and rate-limit guide](https://help.openalex.org/api/authentication).
- Crossref Works: public metadata requests with bounded results and
  concurrency. When configured, the caller's mailto address is supplied for
  the polite pool. Crossref recommends a `mailto` parameter and describes
  public/polite limits in its
  [official REST API access guide](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/).

Provider failures, rate limiting, or malformed responses are explicit; bounded
backoff does not turn a failed lookup into an empty successful search.

## Returned metadata and trust boundary

Records preserve provider/source URL and fetch time and include only fields the
provider actually returned, such as DOI, title, author names, year, journal or
repository, abstract, and open-access/landing-page metadata. Abstracts and
provider metadata are untrusted input. Records are marked abstract-only or
metadata-only; this integration does not fetch article PDFs or claim to have
read a complete paper. Preprint/review status is surfaced only when the
provider's metadata supports that distinction. Citation count is metadata,
not a truth score.

## Validation limits

Provider parsing, limits, errors, rate-limit behavior, untrusted abstract
handling, and orchestrator dispatch have mocked tests. Small live probes
confirmed the documented Works endpoints respond; larger Crossref probes can
be rate-limited and must be retried conservatively. A provider result is not
peer review, verification, or a substitute for the full text.

"""Keyless scholarly-metadata search for OpenAlex Works and Crossref REST."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import research

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
MAX_QUERY_CHARS = 200
MAX_RESULTS = 10
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ABSTRACT_CHARS = 1200
HTTP_TIMEOUT = 8.0
MAX_429_RETRIES = 2
MAX_RETRY_AFTER = 30.0

OPENALEX_FIELDS = (
    "doi,title,authorships,publication_year,primary_location,locations,"
    "abstract_inverted_index,open_access,type,cited_by_count,ids"
)
CROSSREF_FIELDS = (
    "DOI,title,author,published-print,published-online,issued,container-title,"
    "archive,link,license,abstract,type,URL"
)


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doi(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.strip()
    return value[:300] if value.lower().startswith("10.") and "/" in value else None


def _bounded_text(value, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit] or None


def _external_url(value) -> str | None:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value[:1000]
    return None


class _AbstractText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style"):
            self.skipping += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style") and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def _plain_abstract(value) -> str:
    if not isinstance(value, str):
        return ""
    parser = _AbstractText()
    try:
        parser.feed(value[:MAX_ABSTRACT_CHARS * 4])
    except Exception:
        pass
    return " ".join(html.unescape(" ".join(parser.parts)).split())[:MAX_ABSTRACT_CHARS]


def _abstract_from_index(index) -> str:
    if not isinstance(index, dict):
        return ""
    positions = {}
    for word, offsets in index.items():
        if not isinstance(word, str) or not isinstance(offsets, list):
            continue
        for offset in offsets:
            if isinstance(offset, int) and 0 <= offset < 4000:
                positions.setdefault(offset, word[:80])
    return " ".join(positions[pos] for pos in sorted(positions))[:MAX_ABSTRACT_CHARS]


def _year(value):
    if isinstance(value, int) and 1000 <= value <= 9999:
        return value
    return None


def _year_from_crossref(item):
    for field in ("published-print", "published-online", "issued"):
        date = item.get(field) or {}
        if not isinstance(date, dict):
            continue
        parts = date.get("date-parts") or []
        if (isinstance(parts, list) and parts and isinstance(parts[0], list)
                and parts[0] and isinstance(parts[0][0], int)):
            return _year(parts[0][0])
    return None


def _authors(values, crossref=False) -> list[str]:
    result = []
    for author in values if isinstance(values, list) else []:
        if not isinstance(author, dict):
            continue
        if crossref:
            name = " ".join(str(author.get(k) or "").strip()
                            for k in ("given", "family")).strip()
        else:
            details = author.get("author") or {}
            name = details.get("display_name", "") if isinstance(details, dict) else ""
        name = " ".join(str(name).split())[:160]
        if name:
            result.append(name)
        if len(result) == 30:
            break
    return result


def _explicit_review_status(record):
    for key in ("review_status", "peer_reviewed"):
        value = record.get(key)
        if isinstance(value, (str, bool)):
            return value[:120] if isinstance(value, str) else value
    return None


def _normalize_base(provider, provider_url, source_url, landing_url, doi, title,
                    authors, year, journal, repository, abstract, pdf_url, license_value,
                    review_status, citation_count=None):
    fetched = _agora_iso()
    title = _bounded_text(title, 500) or ""
    abstract = abstract[:MAX_ABSTRACT_CHARS]
    provider_url = _external_url(provider_url) or ""
    source_url = _external_url(source_url)
    landing_url = _external_url(landing_url)
    pdf_url = _external_url(pdf_url)
    journal = _bounded_text(journal, 300)
    repository = _bounded_text(repository, 300)
    license_value = _bounded_text(license_value, 500)
    url = landing_url or source_url or provider_url
    normalized = {
        "id": doi or source_url or url,
        "titulo": title,
        "url": url,
        "trecho": abstract,
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "repository": repository,
        "abstract": abstract,
        "landing_url": landing_url,
        "pdf_url": pdf_url,
        "license": license_value,
        "review_status": review_status,
        "provider": provider,
        "provider_url": provider_url,
        "source_url": source_url,
        "fetched_at": fetched,
        "metadata_source": "academic_provider",
        "provider_metadata_untrusted": True,
        "abstract_untrusted": bool(abstract),
        "abstract_kind": "provider_metadata" if abstract else None,
        "content_scope": "abstract_only" if abstract else "metadata_only",
        "full_text_fetched": False,
    }
    if citation_count is not None:
        normalized["citation_count"] = citation_count
        normalized["citation_count_kind"] = "provider_metadata_not_truth_score"
    return normalized


def normalize_openalex(item: dict, provider_url: str) -> dict:
    location = item.get("primary_location") or {}
    if not isinstance(location, dict):
        location = {}
    source = location.get("source") or {}
    if not isinstance(source, dict):
        source = {}
    locations = item.get("locations") or []
    if not isinstance(locations, list):
        locations = []
    location_candidates = ([location] if isinstance(location, dict) else []) + [
        x for x in locations if isinstance(x, dict)
    ]
    # Select the open location itself, rather than attaching its licence to a
    # different, possibly closed primary landing page.
    open_locations = [x for x in location_candidates if x.get('is_oa') is True]
    if open_locations:
        location_candidates = open_locations
    landing = next((x.get("landing_page_url") for x in location_candidates
                    if isinstance(x.get("landing_page_url"), str)
                    and x["landing_page_url"].startswith(("http://", "https://"))), None)
    pdf = next((x.get("pdf_url") for x in location_candidates
                if isinstance(x.get("pdf_url"), str)
                and x["pdf_url"].startswith(("http://", "https://"))), None)
    license_value = next((x.get("license") for x in location_candidates
                          if isinstance(x.get("license"), str) and x["license"]), None)
    repository = next((x.get("source", {}).get("display_name") for x in location_candidates
                       if isinstance(x.get("source"), dict)
                       and x["source"].get("type") == "repository"
                       and x["source"].get("display_name")), None)
    journal = source.get("display_name") if source.get("type") == "journal" else None
    ids = item.get("ids") or {}
    source_url = ids.get("openalex") if isinstance(ids, dict) else None
    source_url = source_url if isinstance(source_url, str) else None
    abstract = _abstract_from_index(item.get("abstract_inverted_index"))
    citation_count = item.get("cited_by_count")
    if (not isinstance(citation_count, int) or isinstance(citation_count, bool)
            or citation_count < 0):
        citation_count = None
    record = _normalize_base(
        "openalex", provider_url, source_url, landing, _doi(item.get("doi")),
        item.get("title"), _authors(item.get("authorships")), _year(item.get("publication_year")),
        journal, repository, abstract, pdf, license_value, _explicit_review_status(item),
        citation_count,
    )
    record['open_access'] = any(x.get('is_oa') is True and
                              (x.get('pdf_url') == pdf if pdf else x.get('landing_page_url') == landing)
                              for x in location_candidates)
    return record


def scientific_sections(record):
    """Label only sections actually extracted; missing study data stays absent."""
    groups={'methods':r'm[eé]tod|method|materials|experimental|amostra|sample',
            'results':r'resulta|results|findings',
            'limitations':r'limita|limitations', 'conclusions':r'conclu|conclusion'}
    out=[]
    for section in (record.get('secoes') or [])[:12]:
        title=str(section.get('titulo') or '')[:160]
        raw_body=str(section.get('texto') or '').strip()
        body=raw_body[:1000]
        if not body: continue
        # PDF page excerpts have no DOM headings. Recognize only explicit
        # heading lines actually present, never infer a method from prose.
        if section.get('pagina') is not None:
            headings=list(re.finditer(
                r'(?im)^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?'
                r'(Materials and methods|Methods|Methodology|Experimental(?: procedure)?|'
                r'Results(?: and discussion)?|Findings|Limitations|Conclusions?|'
                r'Materiais e métodos|Métodos|Resultados(?: e discussão)?|Limitações|Conclusões?)\s*$', raw_body))
            if headings:
                for i, heading in enumerate(headings):
                    text=raw_body[heading.end():headings[i+1].start() if i+1<len(headings) else len(raw_body)].strip()[:1000]
                    if not text: continue
                    label=heading.group(1)
                    kind=next((name for name,pattern in groups.items() if re.search(pattern,label,re.I)),'section')
                    out.append({'title':label,'text':text,'kind':kind,'page':section['pagina'],
                                'source_url':record.get('final') or '', 'extraction_scope':'bounded_section'})
                continue
        kind=next((name for name,pattern in groups.items() if re.search(pattern,title,re.I)),'section')
        out.append({'title':title,'text':body,'kind':kind,'page':section.get('pagina'),
                    'source_url':record.get('final') or '', 'extraction_scope':'bounded_section'})
    return out[:8]


def read_open_text(record, timeout, fetch_pdf):
    """One legal OA candidate, bounded reader, verified bibliographic identity.

    OA/licence metadata is a declaration; network and PDF safety stay in the
    central downloader. No paywall fallback, scraping escalation, or retries.
    """
    license_value=str(record.get('license') or '').lower()
    allowed=record.get('open_access') is True or license_value.startswith(('cc-','https://creativecommons.org/','http://creativecommons.org/'))
    pdf=_external_url(record.get('pdf_url'))
    candidate = pdf or _external_url(record.get('landing_url') or record.get('url'))
    if not allowed or not candidate: return None
    try:
        rec=fetch_pdf({'url':candidate,'titulo':record.get('titulo') or record.get('title',''),
                       'pdf_expected':bool(pdf)},timeout)
        content=str((rec or {}).get('texto') or '')
        import query_intelligence
        normalized=query_intelligence.normalized(content)
        title=query_intelligence.normalized(record.get('title') or record.get('titulo',''))
        terms=set(re.findall(r'[a-z0-9]{3,}',title))
        found=sum(bool(re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',normalized[:12000])) for t in terms)
        doi=str(record.get('doi') or '').casefold()
        identity=(bool(doi) and doi in normalized) or (len(terms)>=3 and found/len(terms)>=0.75)
        if not rec or not rec.get('lida') or len(content.strip())<1000 or not identity:
            return {'oa_attempt':'identity_or_text_insufficient'}
        return {**rec,'content_scope':'document_text','full_text_fetched':True,
                'full_text_url':rec.get('final') or candidate,'access_state':'read','texto_lido':True,
                'extraction_scope':'bounded_text','full_document_read':False,
                'full_text_format':'pdf' if pdf or rec.get('extrator')=='pdf' else 'html',
                'scientific_sections':scientific_sections(rec),
                'oa_attempt':'read_identity_matched'}
    except (research.ResearchErro, OSError, ValueError) as exc:
        # Only an optional retrieval attempt; keep the actual abstract on failure.
        return {'oa_attempt':str(getattr(exc,'codigo',type(exc).__name__))[:80]}


def normalize_crossref(item: dict, provider_url: str) -> dict:
    title_values = item.get("title") or []
    title = title_values[0] if isinstance(title_values, list) and title_values else ""
    kind = str(item.get("type") or "")
    containers = item.get("container-title") or []
    journal = (containers[0] if isinstance(containers, list) and containers
               and kind == "journal-article" else None)
    archives = item.get("archive") or []
    repository = archives[0] if isinstance(archives, list) and archives else None
    links = item.get("link") or []
    links = links if isinstance(links, list) else []
    pdf = next((x.get("URL") for x in links if isinstance(x, dict)
                and "pdf" in str(x.get("content-type") or "").lower()
                and isinstance(x.get("URL"), str)), None)
    licenses = item.get("license") or []
    licenses = licenses if isinstance(licenses, list) else []
    license_value = next((x.get("URL") for x in licenses if isinstance(x, dict)
                          and isinstance(x.get("URL"), str)), None)
    landing = item.get("URL") if isinstance(item.get("URL"), str) else None
    abstract = _plain_abstract(item.get("abstract"))
    source_url = landing
    record = _normalize_base(
        "crossref", provider_url, source_url, landing, _doi(item.get("DOI")), title,
        _authors(item.get("author"), crossref=True), _year_from_crossref(item), journal,
        repository, abstract, pdf, license_value, _explicit_review_status(item),
    )

    dates = []
    for field in ("published-online", "published-print", "issued"):
        value = item.get(field)
        parts = value.get("date-parts") if isinstance(value, dict) else None
        if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
            continue
        nums = parts[0]
        if not 1 <= len(nums) <= 3 or any(type(v) is not int for v in nums):
            continue
        try:
            dt = datetime(nums[0], nums[1] if len(nums) > 1 else 1,
                          nums[2] if len(nums) > 2 else 1, tzinfo=timezone.utc)
        except (ValueError, OverflowError):
            continue
        if dt > datetime.now(timezone.utc):
            continue
        declared = "-".join(str(v).zfill(4 if i == 0 else 2) for i, v in enumerate(nums))
        dates.append((dt, declared, field))
    if dates:
        _, declared, origin = min(dates)
        record["publicado_em"] = declared
        record["publication_date_origin"] = origin
        record["year"] = int(declared[:4])
    record["publication_type"] = kind or "unknown"
    return record


class _RateGate:
    def __init__(self, interval: float):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.blocked_until = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = max(self.next_at, self.blocked_until) - now
            if delay > 0:
                time.sleep(delay)
            self.next_at = time.monotonic() + self.interval

    def defer(self, seconds: float):
        with self.lock:
            self.blocked_until = max(self.blocked_until,
                                     time.monotonic() + max(0.0, seconds))


_OPENALEX_GATE = _RateGate(0.2)
_CROSSREF_GATE = _RateGate(0.21)
_CROSSREF_REQUEST_LOCK = threading.Lock()


def _retry_after(headers) -> float | None:
    value = headers.get("Retry-After") if headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(value)
            return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _get_json(url: str, user_agent: str, gate: _RateGate, open_url=None) -> dict:
    opener = open_url or urllib.request.urlopen
    request = urllib.request.Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "application/json",
    })
    for retry in range(MAX_429_RETRIES + 1):
        gate.wait()
        try:
            with opener(request, timeout=HTTP_TIMEOUT) as response:
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise research.ResearchErro(f"HTTP {status} do provedor acadêmico.",
                                                f"http_{status}")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise research.ResearchErro("Resposta acadêmica acima do limite.", "tamanho")
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise research.ResearchErro("Resposta acadêmica fora do formato JSON.",
                                            "formato") from exc
            if not isinstance(value, dict):
                raise research.ResearchErro("Resposta acadêmica fora do formato.", "formato")
            return value
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = _retry_after(exc.headers)
                delay = max(float(2 ** retry), retry_after or 0.0)
                gate.defer(min(delay, MAX_RETRY_AFTER))
                if retry < MAX_429_RETRIES and delay <= MAX_RETRY_AFTER:
                    continue
                raise research.ResearchErro("Limite do provedor acadêmico (HTTP 429).",
                                            "rate_limited") from None
            raise research.ResearchErro(f"HTTP {exc.code} do provedor acadêmico.",
                                        f"http_{exc.code}") from None
        except research.ResearchErro:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise research.ResearchErro(
                f"Falha de rede no provedor acadêmico ({type(exc).__name__}).", "rede"
            ) from None
    raise research.ResearchErro("Limite do provedor acadêmico (HTTP 429).", "rate_limited")


def _bounded_limit(limit) -> int:
    try:
        return max(1, min(int(limit), MAX_RESULTS, 100))
    except (TypeError, ValueError):
        return MAX_RESULTS


def _query(consulta) -> str:
    query = " ".join(str(consulta or "").split())[:MAX_QUERY_CHARS]
    if len(query) < 2:
        raise research.ResearchErro("Consulta acadêmica curta demais.", "consulta")
    return query


def _user_agent(mailto: str) -> str:
    email_value = (mailto or "").strip()[:254]
    if "@" in email_value and not any(char.isspace() for char in email_value):
        return f"JuliaMobileAcademicResearch/1.0 (mailto:{email_value})"
    return "JuliaMobileAcademicResearch/1.0"


def _mailto_value(mailto: str) -> str:
    value = (mailto or "").strip()[:254]
    if "@" in value and not any(char.isspace() for char in value):
        return value
    return ""


class OpenAlexWorksProvider:
    nome = "openalex"

    def __init__(self, mailto: str = "", open_url=None, gate=None):
        self.mailto = mailto
        self.open_url = open_url
        self.gate = gate or _OPENALEX_GATE

    def buscar(self, consulta: str, limite: int = 6) -> list[dict]:
        params = urllib.parse.urlencode({
            "search": _query(consulta),
            "per-page": _bounded_limit(limite),
            "select": OPENALEX_FIELDS,
        })
        url = f"{OPENALEX_WORKS_URL}?{params}"
        payload = _get_json(url, _user_agent(self.mailto), self.gate, self.open_url)
        results = payload.get("results")
        if not isinstance(results, list):
            raise research.ResearchErro("Resposta OpenAlex sem lista de works.", "formato")
        return [normalize_openalex(item, url) for item in results[:_bounded_limit(limite)]
                if isinstance(item, dict) and (item.get("title") or item.get("doi"))]


class CrossrefWorksProvider:
    nome = "crossref"

    def __init__(self, mailto: str = "", open_url=None, gate=None):
        self.mailto = mailto
        self.open_url = open_url
        self.gate = gate or _CROSSREF_GATE

    def buscar(self, consulta: str, limite: int = 6) -> list[dict]:
        params = {
            "query.bibliographic": _query(consulta),
            "rows": _bounded_limit(limite),
            "select": CROSSREF_FIELDS,
        }
        mailto = _mailto_value(self.mailto)
        if mailto:
            params["mailto"] = mailto
        url = f"{CROSSREF_WORKS_URL}?{urllib.parse.urlencode(params)}"
        with _CROSSREF_REQUEST_LOCK:
            payload = _get_json(url, _user_agent(self.mailto), self.gate, self.open_url)
        message = payload.get("message")
        items = message.get("items") if isinstance(message, dict) else None
        if not isinstance(items, list):
            raise research.ResearchErro("Resposta Crossref sem lista de works.", "formato")
        return [normalize_crossref(item, url) for item in items[:_bounded_limit(limite)]
                if isinstance(item, dict) and (item.get("title") or item.get("DOI"))]


class AcademicResearchProvider:
    """Search fallback from OpenAlex to Crossref without parallel provider calls."""
    nome = "academic"

    def __init__(self, mailto: str = "", openalex=None, crossref=None):
        self.providers = [
            openalex or OpenAlexWorksProvider(mailto=mailto),
            crossref or CrossrefWorksProvider(mailto=mailto),
        ]

    def buscar(self, consulta: str, limite: int = 6) -> list[dict]:
        failures = []
        for provider in self.providers:
            try:
                results = provider.buscar(consulta, limite)
                if results:
                    return results[:_bounded_limit(limite)]
            except research.ResearchErro as exc:
                failures.append(f"{provider.nome}:{exc.codigo}")
        if failures:
            raise research.ResearchErro(
                "Busca acadêmica indisponível (" + ", ".join(failures) + ").",
                "academic_unavailable",
            )
        return []

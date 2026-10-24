"""Bounded gap records for the existing research orchestrator; no I/O or model.

Coverage means extracted information exists, never scientific truth. External
text contributes data only, not instructions, executable code or confidence.
"""
import hashlib
import re
from urllib.parse import urlsplit

from query_intelligence import normalized


def key(text):
    return re.sub(r'[^a-z0-9]+', ' ', normalized(str(text))).strip()


def science_subject(text):
    """Separate requested operations from the subject; retain entity lists/dates."""
    value = re.split(r'[:;]|,?\s+comparando\b|\s+com foco em\b', str(text), maxsplit=1, flags=re.I)[0]
    value = re.sub(r'^(?:faça\s+)?(?:uma\s+)?pesquisa\s+(?:profunda\s+)?sobre\s+', '', value, flags=re.I)
    value = re.sub(r'^compare\s+(?:os\s+)?(?:estudos|artigos)(?:\s+científicos)?\s+(?:sobre|de)\s+', '', value, flags=re.I)
    return re.sub(r'\s+', ' ', value).strip(' ,.!?')[:180]


def read(source):
    return (source.get('texto_lido') is True and bool(str(source.get('trecho') or '').strip())
            and source.get('content_scope') not in ('feed_metadata', 'metadata_only', 'abstract_only'))


def identify(job, evidence):
    objective = str(job.get('objetivo') or '')
    if not objective:
        return []
    if re.search(r'\b(imagens?|fotos?|videos?)\b', normalized(objective)) and not re.search(
            r'analis|evidenc|compar|transcri', normalized(objective)):
        return []  # Retrieval/gallery intent does not require reading an article.
    evidence = [e for e in evidence[:80] if isinstance(e, dict)]
    scientific = bool(re.search(r'estud|cientific|papers?|metod|estado solido', normalized(objective)))
    compare = bool(re.search(r'compar|diferenc', normalized(objective)))
    required = 2 if scientific and compare else 1
    readable = [e for e in evidence if read(e)]
    if scientific:
        readable = [e for e in readable if re.fullmatch(r'10\.\d{4,9}/\S+', str(e.get('doi') or ''))
                    or e.get('publication_type') in ('journal-article','proceedings-article','preprint','scholarlyarticle')]
    definitions = [('original_text', 'Trecho original pertinente', 'primary source original text', readable)]
    if scientific:
        definitions = [('original_text', 'Texto científico além do abstract', 'open access full text', readable)]
        dimensions = [('methods', 'Métodos e amostra', 'methods sample experimental'),
                      ('results', 'Resultados com métrica e unidade', 'results measurements units'),
                      ('conditions', 'Condições experimentais', 'experimental conditions temperature pressure'),
                      ('limitations', 'Limitações declaradas', 'limitations study')]
        for dimension, label, query_terms in dimensions:
            if not compare and not re.search({'methods':r'metod|amostra', 'results':r'resulta|metrica',
                    'conditions':r'condic', 'limitations':r'limita'}[dimension], normalized(objective)):
                continue
            matched = []
            for e in readable:
                sections = e.get('scientific_sections') or []
                for section in sections[:8]:
                    text = str(section.get('text') or '')
                    if len(text.strip()) < 20:
                        continue
                    kind = section.get('kind')
                    if dimension == 'conditions':
                        qualifies = kind == 'methods' and bool(re.search(
                            r'\b\d+(?:[.,]\d+)?\s*(?:°?\s*[cCkK]\b|[mMkK]?[pP][aA]\b|cycles?\b|ciclos?\b)', text))
                    elif dimension == 'results':
                        import evidence_graph
                        qualifies = kind == 'results' and any(q.get('unidade') for q in evidence_graph.extrair_quantidades(text))
                    else:
                        qualifies = kind == dimension
                    if qualifies:
                        matched.append(e)
                        break
            definitions.append((dimension, label, query_terms, matched))
    searches = [s for s in job.get('plano', []) if s.get('tipo') == 'busca']
    attempted = [str(s.get('alvo', '')) for s in searches if s.get('status') in ('feita', 'falhou')]
    planned = {key(s.get('alvo', '')) for s in searches}
    remaining = max(0, job.get('orcamento', {}).get('buscas', 0) - job.get('usados', {}).get('buscas', 0))
    candidates = []
    for e in evidence:
        url = str(e.get('url') or '')
        try:
            parsed = urlsplit(url)
            if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username and url not in candidates:
                candidates.append(url[:500])
        except ValueError:
            continue
    # A discovered DOI is a precise query identifier, never a fabricated OA URL.
    doi = next((str(e.get('doi', '')).removeprefix('https://doi.org/') for e in evidence
                if re.fullmatch(r'(?:https://doi.org/)?10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+', str(e.get('doi', '')))), '')
    stem = re.sub(r'[\x00-\x1f"`<>]', ' ', objective).strip()[:140]
    if scientific:
        stem = science_subject(stem)
    anchor = ('"' + doi[:120] + '"') if scientific and doi else stem
    if re.search(r'noticia|acontecimentos?', normalized(objective)):
        lead = next((e for e in evidence if e.get('content_scope') == 'feed_metadata' and e.get('titulo')), None)
        if lead:
            title = re.sub(r'[\x00-\x1f"`<>]', ' ', str(lead['titulo']))[:110]
            anchor = '"' + title + '" ' + stem[:90]
    out = []
    for index, (dimension, label, terms, matched) in enumerate(definitions[:6]):
        identities = {str(e.get('doi') or e.get('url') or e.get('id')).casefold() for e in matched}
        resolved = len(identities) >= required
        query = (('papers ' if scientific else '') + anchor + ' ' + terms)[:240]
        previous = [q for q in attempted if key(q) == key(query)]
        out.append({'id': hashlib.sha256((str(job.get('id', '')) + ':' + dimension).encode()).hexdigest()[:16],
            'dimension': dimension, 'description': label, 'subquestion': query,
            'expected_data': label, 'relevance': 'necessário para responder ao pedido',
            'evidence_ids': list(dict.fromkeys(str(e['id']) for e in matched if e.get('id')))[:8],
            'candidate_sources': candidates[:4], 'previous_attempts': previous[:4],
            'priority': index + 1, 'status': 'RESOLVED' if resolved else 'OPEN',
            'query': query if not resolved and key(query) not in planned and remaining else '',
            'budget': {'remaining_searches': remaining, 'max_new_searches': 1},
            'required_publications': required, 'observed_publications': len(identities),
            'scope': 'bounded extracted evidence; no claim of full study coverage'})
    return out


def decision(job, gaps):
    used = job.get('usados', {})
    if job.get('status') in ('cancelada', 'pausada', 'interrompida'):
        return {'action': 'STOP_PARTIAL', 'reason': 'interrupted_or_cancelled', 'gap_ids': []}
    if used.get('research_outcome', {}).get('state') == 'blocked':
        return {'action': 'STOP_PARTIAL', 'reason': 'provider_blocked', 'gap_ids': []}
    remaining = max(0, job.get('orcamento', {}).get('buscas', 0) - used.get('buscas', 0))
    replans = max(0, job.get('orcamento', {}).get('replans', 0) - used.get('replans', 0))
    pages = max(0, job.get('orcamento', {}).get('paginas', 0) - used.get('paginas', 0))
    actionable = [g for g in gaps if g['status'] == 'OPEN' and g.get('query')]
    if actionable and remaining and pages and replans:
        return {'action': 'REPLAN', 'reason': 'required_data_missing', 'gap_ids': [g['id'] for g in actionable[:4]]}
    if any(g['status'] == 'OPEN' for g in gaps):
        return {'action': 'STOP_PARTIAL', 'reason': 'budget_or_no_new_query', 'gap_ids': []}
    if not gaps and not job.get('midia'):
        return {'action': 'STOP_PARTIAL', 'reason': 'no_extracted_data', 'gap_ids': []}
    return {'action': 'SYNTHESIZE', 'reason': 'extracted_data_available_requires_validation', 'gap_ids': []}

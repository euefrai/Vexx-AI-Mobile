"""Discover Python API pages from the public Sphinx data inventory, never JS.

Inventory references are discovery only; the normal article reader must open
the document before its contents can become evidence.
"""
import re
import time
import urllib.parse
import zlib
import hashlib
import os
from datetime import datetime, timezone

INVENTORY = 'https://docs.python.org/3/objects.inv'
_CACHE = None
MAX_COMPRESSED = 512 * 1024
MAX_EXPANDED = 2 * 1024 * 1024


def parse_inventory(blob):
    if len(blob) > MAX_COMPRESSED:
        raise ValueError('Inventory too large')
    parts = blob.split(b'\n', 4)
    if len(parts) != 5 or parts[0] != b'# Sphinx inventory version 2' or parts[1] != b'# Project: Python':
        raise ValueError('Unexpected documentation inventory')
    reader = zlib.decompressobj()
    text = reader.decompress(parts[4], MAX_EXPANDED + 1)
    if len(text) > MAX_EXPANDED or not reader.eof or reader.unconsumed_tail or reader.unused_data:
        raise ValueError('Invalid or oversized compressed inventory')
    return text.decode('utf-8').splitlines()[:30000]


def search(query, limit=6, timeout=6):
    import research
    global _CACHE
    if not re.search(r'\b(python|asyncio)\b', query, re.I):
        return []
    if not _CACHE or _CACHE[0] <= time.monotonic():
        research.url_segura(INVENTORY)
        # Fixed URL. The opener rejects redirects and revalidates the resolved
        # address when connecting. Binary inventory data never reaches LLM.
        with research._abrir(INVENTORY, timeout=min(8, timeout)) as response:
            if getattr(response, 'status', 200) != 200:
                return []
            lines = parse_inventory(response.read(MAX_COMPRESSED + 1))
        _CACHE = (time.monotonic() + 6 * 3600, lines)
    tokens = set(re.findall(r'[a-z_][a-z_0-9]*', query.casefold()))
    qualified = set(re.findall(r'\b[a-z_]\w*(?:\.[a-z_]\w*)+\b', query.casefold()))
    tokens -= {'compare', 'analyze', 'print', 'python', 'verifique', 'fontes', 'oficial', 'documentacao'}
    candidates = []
    for line in _CACHE[1]:
        fields = line.split(' ', 4)
        if len(fields) != 5 or not fields[1].startswith('py:'):
            continue
        name, _, _, path, _ = fields
        if qualified and name.casefold() not in qualified:
            continue
        leaf = name.rsplit('.', 1)[-1].casefold()
        if len(leaf) < 4 or leaf not in tokens:
            continue
        url = urllib.parse.urljoin('https://docs.python.org/3/', path.replace('$', name))
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'docs.python.org' or not parsed.path.startswith('/3/'):
            continue
        score = 20 if name.casefold() in qualified else 3 if fields[1] == 'py:module' else 5
        candidates.append((score, name, url))
    candidates.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    # Multiple APIs often share one document. Merge their discovered names
    # before canonical URL dedupe, so a comparison does not lose an entity.
    grouped = {}
    for _, name, url in candidates:
        parsed = urllib.parse.urlsplit(url)
        key = urllib.parse.urlunsplit(parsed._replace(fragment=''))
        entry = grouped.setdefault(key, {'url': url, 'names': []})
        if name not in entry['names']:
            entry['names'].append(name)
    out = []
    for entry in list(grouped.values())[:min(10, max(1, limit))]:
        out.append({'titulo': ', '.join(entry['names'][:4]) + ' — Documentação oficial do Python', 'url': entry['url'],
                    'trecho': 'Referência de API localizada no inventário público; documento ainda não lido.',
                    'origem': 'python-docs', 'tipo': 'tecnico', 'status': 'encontrada',
                    'meta': {'discovery_method': 'sphinx_inventory', 'api_names': entry['names'][:8]}})
    return out


def read_authority(query, url, record, timeout=3):
    """Attest a read API page against an independently fetched PSF inventory.

    This establishes publisher/document identity, never factual support for an
    answer. Other publishers and generic Python pages remain unverified.
    """
    if os.environ.get('JULIA_PYTHON_DOCS_DISCOVERY','1')=='0' or not record.get('texto_lido'):
        return None
    names=set(re.findall(r'\b[a-z_]\w*(?:\.[a-z_]\w*)+\b', query.casefold()))
    if not names or len(names)>4:return None
    parsed=urllib.parse.urlsplit(url)
    target=urllib.parse.urlunsplit(parsed._replace(fragment='',query=''))
    if parsed.scheme!='https' or parsed.netloc!='docs.python.org' or not parsed.path.startswith('/3/'):
        return None
    read_text=record.get('texto') or ''
    scope=read_text+' '+' '.join(h.get('text','') for p in record.get('answer_passages',[])
                               for h in p.get('section_path',[]))
    scope=re.sub(r'\s*\.\s*','.',scope).casefold()
    if not read_text.strip() or not all(re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',scope) for n in names):
        return None
    for row in search(query,timeout=timeout):
        actual=urllib.parse.urlsplit(row['url'])._replace(fragment='',query='').geturl()
        found={n.casefold() for n in row['meta']['api_names']}
        if actual==target and names<=found:
            return {'method':'psf_inventory_and_read_page','publisher':'Python Software Foundation',
                    'inventory_url':INVENTORY,'document_url':target,
                    'inventory_sha256':hashlib.sha256('\n'.join(_CACHE[1]).encode()).hexdigest(),
                    'api_names':sorted(names),'verified_at':datetime.now(timezone.utc).isoformat()}
    return None


def has_read_authority(source, query):
    """Validate server-recorded provenance; do not trust a model's boolean."""
    proof=source.get('source_authority') or {}
    if not isinstance(proof,dict):return False
    api_names=proof.get('api_names')
    if (not isinstance(api_names,list) or not 1<=len(api_names)<=4
            or any(not isinstance(n,str) or not re.fullmatch(r'\w+(?:\.\w+)+',n) for n in api_names)):
        return False
    names=set(re.findall(r'\b[a-z_]\w*(?:\.[a-z_]\w*)+\b', query.casefold()))
    try:
        parsed=urllib.parse.urlsplit(source.get('url',''))
        url=urllib.parse.urlunsplit(parsed._replace(fragment='',query=''))
        verified=datetime.fromisoformat(proof.get('verified_at',''))
    except (ValueError,TypeError,AttributeError):return False
    return bool(source.get('texto_lido') is True and source.get('content_scope') not in ('abstract_only','metadata_only','feed_metadata')
        and proof.get('method')=='psf_inventory_and_read_page'
        and proof.get('publisher')=='Python Software Foundation' and proof.get('inventory_url')==INVENTORY
        and parsed.scheme=='https' and parsed.netloc=='docs.python.org' and parsed.path.startswith('/3/')
        and proof.get('document_url')==url and verified.tzinfo is not None
        and re.fullmatch(r'[0-9a-f]{64}',str(proof.get('inventory_sha256','')))
        and names and names<=set(api_names))

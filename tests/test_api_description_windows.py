"""Locate unlabeled API bodies without broadening output or factual support."""
import hashlib

import pytest

import evidence_graph as eg
import web_extract as we


FILLER = '<p>' + ('An unrelated manual paragraph about files and event loops. ' * 30) + '</p>'
DESCRIPTION = ('An asynchronous context manager that can be used to limit the amount '
               'of time spent waiting on something.')
EXPIRATION = ('When the deadline expires, the current task is cancelled and the resulting '
              'cancellation is transformed into TimeoutError.')
URL = 'https://reference.example/manual'


def document(api='asyncio.timeout', before=10):
    return ('<main><h1>Coroutines and tasks</h1>' + FILLER * before +
            '<section><h2>Timeouts</h2><dl><dt id="operation">' + api + '(delay)</dt>'
            '<dd><p>' + DESCRIPTION + '</p><p>' + EXPIRATION + '</p></dd></dl></section>' +
            FILLER * 8 + '<section><h2>Eager task execution</h2><dl>'
            '<dt>asyncio.eager_task_factory()</dt><dd><p>Immediate execution is a semantic '
            'change. The task behavior changes and applications may need adjustments.</p>'
            '</dd></dl></section></main>')


def extract(html, query, **kwargs):
    return we.extrair_pagina(html, URL, query, usar_trafilatura=False, **kwargs)


@pytest.mark.parametrize('api', ['asyncio.timeout', 'widget.deadline'])
@pytest.mark.parametrize('before', [0, 5, 12])
def test_unlabeled_api_description_is_retained_along_with_expiration(api, before):
    query = 'O que faz ' + api + ' e o que acontece quando o prazo expira?'
    rec = extract(document(api, before), query)
    assert DESCRIPTION in rec['texto'] and EXPIRATION in rec['texto']
    assert len(rec['texto']) <= 8000 and len(rec['answer_passages']) <= 8
    for body in (DESCRIPTION, EXPIRATION):
        passage = next(p for p in rec['answer_passages'] if body in p['text'])
        assert passage['section_path'][-1]['text'] == api + '(delay)'
        assert passage['section_path'][-1]['level'] == 7
    if before:
        assert rec['document_scan']['late_passages'] >= 2


def test_selected_bodies_and_signature_offsets_remain_literal():
    html = document()
    rec = extract(html, 'O que faz asyncio.timeout?')
    full = we._normalizar(extract(html, '', teto=100000)['texto'])
    digest = hashlib.sha256(full.encode()).hexdigest()
    for passage in rec['answer_passages']:
        span = passage['source_span']
        assert full[span['start']:span['end']] == passage['text']
        assert span['sha256'] == digest
        returned = passage['text_span']
        assert rec['texto'][returned['start']:returned['end']] == passage['text']
        signature = passage['section_path'][-1]
        scope = signature['source_span']
        assert full[scope['start']:scope['end']] == signature['text']
        assert scope['sha256'] == digest


def test_metadata_title_and_fragment_cannot_assign_a_different_api_body():
    html = document('asyncio.other_operation')
    rec = we.extrair_pagina('<title>asyncio.timeout</title>' + html,
        URL + '#asyncio.timeout', 'O que faz asyncio.timeout?', usar_trafilatura=False)
    assert DESCRIPTION not in rec['texto'] and EXPIRATION not in rec['texto']
    rec['texto_lido'] = True
    assert not eg.requirement_coverage('O que faz asyncio.timeout?', [rec])['passages']


def test_locating_body_does_not_make_unparsed_expiration_request_complete():
    query = 'O que faz asyncio.timeout e o que acontece quando o prazo expira?'
    rec = extract(document(), query)
    rec['texto_lido'] = True
    coverage = eg.requirement_coverage(query, [rec])
    assert DESCRIPTION in rec['texto'] and EXPIRATION in rec['texto']
    assert not coverage['complete']
    assert any(r['attribute'] == 'original_objective' and r['state'] != 'SUPPORTED'
               for r in coverage['requirements'])

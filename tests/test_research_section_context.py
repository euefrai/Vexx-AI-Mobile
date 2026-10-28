"""Literal section navigation, separate from discovery and semantic verification."""
import copy
import hashlib

import pytest

import evidence_graph as eg
import web_extract as we

URL = 'https://example.org/history'
QUERY = 'Quais foram as causas e consequências da Revolta Aurora?'
FILLER = '<p>' + ('Relato de viagens e atividades administrativas locais. ' * 30) + '</p>'
CAUSE = 'A distribuição das terras excluía as famílias que viviam na região.'
AFTER = 'As eleições passaram a ocorrer com participação dos moradores.'


def document(title='Revolta Aurora', extra=''):
    return ('<main><h1>' + title + '</h1>' + FILLER * 12 +
            '<h2>Antecedentes</h2><p>' + CAUSE + '</p>' +
            '<p>Os trabalhadores também enfrentavam salários atrasados.</p>' +
            '<h2>Consequências</h2><p>' + AFTER + '</p>' + extra + '</main>')


def extract(html, query=QUERY, **kwargs):
    return we.extrair_pagina(html, URL, query, usar_trafilatura=False, **kwargs)


def test_heading_selects_all_short_section_paragraphs_without_body_keywords():
    rec = extract(document())
    assert all(t in rec['texto'] for t in (CAUSE, AFTER, 'salários atrasados'))
    assert len(rec['texto']) <= 8000
    assert len(rec['answer_passages']) <= 8
    assert rec['document_scan']['late_passages'] >= 3


def test_heading_path_and_both_text_coordinate_systems_are_literal():
    html = document()
    rec = extract(html)
    full = we._normalizar(extract(html, '', teto=100000)['texto'])
    digest = hashlib.sha256(full.encode()).hexdigest()
    assert rec.get('answer_passages')
    for p in rec['answer_passages']:
        span = p['source_span']
        assert full[span['start']:span['end']] == p['text']
        assert span['sha256'] == digest
        span = p['text_span']
        assert rec['texto'][span['start']:span['end']] == p['text']
        path = p['section_path']
        assert path[0]['text'] == 'Revolta Aurora'
        assert path[-1]['text'] == p['section']
        for h in path:
            s = h['source_span']
            assert full[s['start']:s['end']] == h['text']
            assert s['sha256'] == digest
    assert rec['answer_passages'] == extract(html)['answer_passages']


def test_sibling_heading_ends_previous_section_and_nested_heading_keeps_ancestry():
    extra = ('<h2>Notas editoriais</h2><p>EDITORIAL SEM RELAÇÃO COM A PERGUNTA.</p>'
             '<h2>Antecedentes</h2><h3>Economia</h3><p>Os impostos eram cobrados antecipadamente.</p>')
    rec = extract(document(extra=extra))
    assert 'EDITORIAL SEM' not in rec['texto']
    nested = next(p for p in rec['answer_passages'] if 'impostos' in p['text'])
    assert [h['text'] for h in nested['section_path']] == ['Revolta Aurora', 'Antecedentes', 'Economia']


def test_heading_context_is_partial_not_a_verified_causal_relation():
    rec = extract(document())
    rec['texto_lido'] = True
    coverage = eg.requirement_coverage(QUERY, [rec])
    assert {r['state'] for r in coverage['requirements']} == {'PARTIALLY_SUPPORTED'}
    assert not coverage['complete']
    assert {p['support_label'] for p in coverage['passages']} == {'PARTIAL_SUPPORT'}


@pytest.mark.parametrize('title', ['Revolta Boreal', 'Revolta Aurora II'])
def test_other_subject_or_variant_does_not_inherit_context(title):
    rec = extract(document(title))
    rec['texto_lido'] = True
    assert not eg.requirement_coverage(QUERY, [rec])['passages']


@pytest.mark.parametrize('updates', [{'texto_lido': False}, {'texto_lido': True, 'content_scope': 'abstract_only'},
                                    {'texto_lido': True, 'content_scope': 'metadata_only'}])
def test_unread_or_metadata_cannot_supply_context(updates):
    rec = extract(document())
    rec.update(updates)
    assert not eg.requirement_coverage(QUERY, [rec])['passages']


def test_section_metadata_cannot_supply_complete_answer_or_survive_bad_hash():
    rec = extract(document())
    rec['texto_lido'] = True
    assert eg.requirement_coverage(QUERY, [rec])['passages']
    bad = copy.deepcopy(rec)
    for p in bad['answer_passages']:
        p['section_path'][0]['source_span']['sha256'] = 'bad'
    assert not eg.requirement_coverage(QUERY, [bad])['passages']


def test_heading_without_body_is_not_evidence():
    rec = extract('<main><h1>Revolta Aurora</h1>' + FILLER * 12 +
                  '<h2>Antecedentes</h2><h2>Consequências</h2></main>')
    rec['texto_lido'] = True
    assert not eg.requirement_coverage(QUERY, [rec])['passages']


def test_unaligned_optional_extraction_never_inherits_dom_headings(monkeypatch):
    independent = ('Trecho sem relação com os títulos do documento. ' * 250 +
                   'A Revolta Boreal foi causada por disputas de terras entre famílias.')
    monkeypatch.setattr(we, '_trafilatura', lambda *a: independent)
    monkeypatch.setattr(we, '_extruct', lambda *a: {})
    rec = we.extrair_pagina(document(), URL, QUERY)
    assert all(not p.get('section_path') for p in rec.get('answer_passages', []))
    rec['texto_lido'] = True
    assert not eg.requirement_coverage(QUERY, [rec])['passages']


def test_explicit_causal_sentence_can_still_have_direct_support():
    rec = extract(document(extra='<h2>Causas</h2><p>Registros administrativos da região.</p>'
                           '<p>Revolta Aurora foi causada pela disputa de terras.</p>'))
    rec['texto_lido'] = True
    reqs = eg.requirement_coverage(QUERY, [rec])['requirements']
    assert next(r for r in reqs if r['attribute'] == 'causes')['state'] == 'SUPPORTED'


def test_section_paths_reach_storage_graph_and_synthesis_without_becoming_complete(tmp_path):
    import json
    import pc_agent
    import research_agents as ra

    db = pc_agent.open_db(tmp_path / 'section-reading.sqlite')
    try:
        job = ra.criar_job(db, 'qa-sections', QUERY, manual='pro')
        rec = extract(document())
        hit = {'id': 'history', 'url': URL, 'titulo': 'Revolta Aurora', 'trecho': 'História da Revolta Aurora.'}
        evidence = ra.agente_analista(db, job, {'alvo': QUERY}, [hit],
                                     lambda url: {**rec, 'final': url, 'texto_lido': True}, teto_paginas=1)
        assert len(evidence) == 1
        stored = ra.listar_evidencias(db, job['owner'], job['id'])
        assert stored[0]['answer_passages'] == evidence[0]['answer_passages']
        assert eg.requirement_coverage(QUERY, stored)['passages']
        assert not eg.requirement_coverage(QUERY, stored)['complete']
        assert not any(e['tipo'] == 'evidence_graph_failed' for e in ra.eventos_desde(db, job['owner'], job['id']))

        captured = []
        def writer(messages, timeout):
            captured.append(json.loads(messages[-1]['content']))
            return '{}'
        ra.agente_sintetizador(db, job, stored, [], writer)
        source = captured[0]['sources'][0]
        assert all(p['section_path'] for p in source['passage_ranges'])
        assert {r['state'] for r in captured[0]['requirements']} == {'PARTIALLY_SUPPORTED'}
        assert ra.listar_evidencias(db, 'another-owner', job['id']) == []
    finally:
        db.close()


def test_eight_long_passages_fit_existing_evidence_storage_limit(tmp_path):
    import pc_agent
    import research_agents as ra

    # Realistic repeated headings/paragraphs must not overflow the 12k source
    # record just because navigation metadata was added.
    paragraphs = ''.join('<p>' + (f'Registro {i}: ' + CAUSE + ' ' + AFTER + ' ') * 5 + '</p>' for i in range(10))
    html = '<main><h1>Revolta Aurora</h1>' + FILLER * 12 + '<h2>Antecedentes</h2>' + paragraphs + '</main>'
    rec = extract(html)
    assert len(rec['answer_passages']) == 8
    db = pc_agent.open_db(tmp_path / 'bounded.sqlite')
    try:
        job = ra.criar_job(db, 'qa-sections', QUERY, manual='pro')
        evidence = ra.agente_analista(db, job, {'alvo': QUERY},
            [{'id': 'history', 'url': URL, 'titulo': 'Revolta Aurora'}],
            lambda url: {**rec, 'final': url, 'texto_lido': True}, teto_paginas=1)
        assert len(evidence) == 1
        assert ra.listar_evidencias(db, job['owner'], job['id'])[0]['answer_passages']
    finally:
        db.close()


def test_real_h1_outside_article_keeps_explicit_separate_coordinates():
    html = '<h1>Revolta Aurora</h1>' + document().replace('<h1>Revolta Aurora</h1>', '')
    rec = extract(html)
    rec['texto_lido'] = True
    for p in rec['answer_passages']:
        heading = p['section_path'][0]
        assert heading['source_span'] == {'start': 0, 'end': len('Revolta Aurora'),
            'scope': 'normalized_dom_heading', 'sha256': hashlib.sha256('Revolta Aurora'.encode()).hexdigest()}
        assert heading['extraction_sha256'] == p['source_span']['sha256']
    assert eg.requirement_coverage(QUERY, [rec])['passages']
    assert not eg.requirement_coverage(QUERY, [rec])['complete']


def test_external_heading_cannot_cross_another_topic_or_navigation():
    for prefix in ('<h1>Revolta Aurora</h1><h2>Outro assunto</h2>',
                   '<nav><h1>Revolta Aurora</h1></nav>',
                   '<article><h1>Revolta Aurora</h1></article>'):
        rec = extract(prefix + document().replace('<h1>Revolta Aurora</h1>', ''))
        rec['texto_lido'] = True
        assert not eg.requirement_coverage(QUERY, [rec])['passages']


def test_article_header_h1_scopes_its_own_container_only():
    body = document().removeprefix('<main><h1>Revolta Aurora</h1>').removesuffix('</main>')
    header = '<header><h1>Revolta Aurora</h1></header>'
    rec = extract('<main>' + header + '<div><div class="article">' + body + '</div></div></main>')
    rec['texto_lido'] = True
    assert eg.requirement_coverage(QUERY, [rec])['passages']
    unrelated = extract(header + '<main><div><div class="article">' + body + '</div></div></main>')
    unrelated['texto_lido'] = True
    assert not eg.requirement_coverage(QUERY, [unrelated])['passages']


def test_deduplicated_metadata_is_lossless_and_does_not_bypass_storage_budget():
    import json
    import json_store
    import research_agents as ra

    passage = {'id': 'p', 'text': 'Texto literal. ' * 300, 'section_id': 's',
               'section_path': [{'text': 'Antecedentes'}]}
    source = {'answer_passages': [passage], 'trecho_usado': passage['text'],
              'scientific_sections': [{'title': 'Antecedentes', 'text': passage['text']}],
              'sections': [{'text': passage['text']}]}
    unchanged = copy.deepcopy(source)
    encoded = ra._encode_evidence_metadata(source)
    assert len(encoded) <= 12000
    assert ra._restore_evidence_metadata(json.loads(encoded)) == source == unchanged
    with pytest.raises(json_store.JSONLimitError):
        ra._encode_evidence_metadata({**source, 'unique': 'z' * 12001})
    legacy = {'answer_passages': [{'id': 'old', 'text': 'Older literal text.'}]}
    assert ra._restore_evidence_metadata(copy.deepcopy(legacy)) == legacy


@pytest.mark.parametrize('body', [
    'Se os impostos aumentassem, a Revolta Aurora poderia ocorrer no futuro.',
    'Os registros não permitem confirmar as causas ou os efeitos do conflito.',
    'Revolta Boreal foi causada por uma disputa entre autoridades locais.',
])
def test_section_context_never_promotes_conditionals_unknowns_or_other_subjects(body):
    rec = extract('<main><h1>Revolta Aurora</h1>' + FILLER * 12 +
                  '<h2>Antecedentes</h2><p>' + body + '</p></main>')
    rec['texto_lido'] = True
    coverage = eg.requirement_coverage(QUERY, [rec])
    assert not coverage['complete']
    assert not any(p['support_label'] == 'DIRECT_SUPPORT' for p in coverage['passages'])

"""Real synthesis plumbing with controlled sources/writer/reviewer, no network."""
import copy
import json

import pytest

import pc_agent
import research_agents as ra

QUERY = 'Quem fundou a Atlas, em que ano foi fundada e quais produtos fabrica?'
FOUNDING = 'Atlas foi fundada em 1981 por Rita Silva.'
PRODUCTS = 'Atlas fabrica motores elétricos e geradores.'


@pytest.fixture
def context(tmp_path):
    db = pc_agent.open_db(tmp_path / 'context.sqlite')
    job = ra.criar_job(db, 'qa-context', QUERY, conv='qa-chat')
    yield db, job
    db.close()


def source(ident, text=FOUNDING, score=10, **kwargs):
    return dict(id=ident, titulo='Atlas', dominio='example.org', url=f'https://example.org/{ident}',
                trecho=text, texto_lido=True, access_state='read', score=score, **kwargs)


def repeated():
    return [source(f'founder-{i}', score=100-i) for i in range(6)]


def capture(context, evidence):
    messages = []
    def writer(prompt, timeout):
        messages.append(json.loads(prompt[-1]['content']))
        return '{}'
    db, job = context
    ra.agente_sintetizador(db, job, evidence, [], writer)
    return messages[0]


def test_only_source_for_another_aspect_survives_six_source_cap(context):
    items = repeated() + [source('products', PRODUCTS, score=0)]
    original = copy.deepcopy(items)
    payload = capture(context, items)
    assert 'products' in [s['evidence_id'] for s in payload['sources']]
    assert len(payload['sources']) == 6
    assert {r['state'] for r in payload['requirements']} == {'SUPPORTED'}
    assert items == original


def test_stored_requirement_labels_cannot_replace_literal_support(context):
    fake = source('fake', 'Uma notícia sobre esportes e lazer.', score=1000,
                  answerability={'aspects': ['Produtos'], 'state': 'DIRECT_ANSWER'},
                  answer_passages=[{'id': 'fake-p', 'text': 'Uma notícia sobre esportes e lazer.',
                                    'requirement_ids': ['invented'], 'support_label': 'DIRECT_SUPPORT'}])
    payload = capture(context, [fake] + repeated() + [source('products', PRODUCTS, score=-1)])
    assert 'products' in [s['evidence_id'] for s in payload['sources']]


@pytest.mark.parametrize('updates', [dict(texto_lido=False, access_state='snippet_only'),
                                    dict(content_scope='abstract_only')])
def test_unread_or_abstract_cannot_displace_read_answer(context, updates):
    fake = source('not-full-text', PRODUCTS, score=999)
    fake.update(updates)
    payload = capture(context, [fake] + repeated() + [source('products', PRODUCTS, score=0)])
    assert 'products' in [s['evidence_id'] for s in payload['sources']]
    if not fake['texto_lido']:
        assert 'not-full-text' not in [s['evidence_id'] for s in payload['sources']]


def passage_source():
    texts = [(FOUNDING + ' Relato administrativo neutro.' * 25),
             (FOUNDING + ' Relato histórico complementar.' * 25),
             (PRODUCTS + ' Descrição dos equipamentos industriais.' * 7)]
    text = '\n\n'.join(texts)
    cursor = 0
    passages = []
    for i, chunk in enumerate(texts):
        passages.append({'id': f'p{i}', 'text': chunk,
                         'text_span': {'start': cursor, 'end': cursor+len(chunk),
                                       'scope': 'returned_extracted_text'}})
        cursor += len(chunk) + 2
    return source('multi-section', texts[0], texto=text, answer_passages=passages)


def test_passage_budget_keeps_different_aspects_instead_of_repetitions(context):
    item = passage_source()
    payload = capture(context, [item])
    offered = payload['sources'][0]
    assert PRODUCTS in offered['excerpt']
    assert FOUNDING in offered['excerpt']
    assert len(offered['excerpt']) <= 1800
    assert {r['state'] for r in payload['requirements']} == {'SUPPORTED'}
    for p in offered['passage_ranges']:
        assert offered['excerpt'][p['start']:p['end']] in item['texto']


def test_content_outside_offered_text_cannot_gain_selection_priority(context):
    far = source('beyond-budget', 'Texto genérico sobre administração. ' * 90 + PRODUCTS, score=-10)
    payload = capture(context, repeated() + [far])
    assert 'beyond-budget' not in [s['evidence_id'] for s in payload['sources']]
    assert next(r for r in payload['requirements'] if r['aspect'] == 'Produtos')['state'] != 'SUPPORTED'


def test_failed_writer_preserves_complementary_literal_passages(context):
    item = source('two-aspects', FOUNDING, texto=FOUNDING+'\n\n'+PRODUCTS,
                  answer_passages=[
                      {'id':'founding','text':FOUNDING,'text_span':{'start':0,'end':len(FOUNDING)}},
                      {'id':'products','text':PRODUCTS,'text_span':{'start':len(FOUNDING)+2,
                          'end':len(FOUNDING)+2+len(PRODUCTS)}}])
    db, job = context
    result = ra.agente_sintetizador(db, job, [item], [], lambda *_: '{"points":[]}')
    assert not result['llm']
    assert FOUNDING in result['texto'] and PRODUCTS in result['texto']
    assert '> '+FOUNDING in result['texto'] and '> '+PRODUCTS in result['texto']
    assert result['references'] == {'E1':'two-aspects'}


def test_stale_passage_does_not_enter_model_context(context):
    item = source('stale', FOUNDING, texto=FOUNDING, answer_passages=[
        {'id': 'stale-p', 'text': PRODUCTS, 'text_span': {'start': 0, 'end': len(PRODUCTS)}}])
    offered = capture(context, [item])['sources'][0]
    assert PRODUCTS not in offered['excerpt']


def test_without_parsed_aspects_original_relevance_order_is_preserved(context):
    context[1]['objetivo'] = 'Resuma o material disponível sobre a Atlas.'
    items = [source(f's{i}', score=i) for i in range(8)]
    offered = capture(context, items)['sources']
    assert [s['evidence_id'] for s in offered] == ['s7', 's6', 's5', 's4', 's3', 's2']


@pytest.mark.parametrize('updates', [dict(relevante=False), dict(vertical={'eligible': False})])
def test_ineligible_read_source_cannot_gain_priority_or_reach_writer(context, updates):
    rejected = source('rejected', PRODUCTS, score=999, **updates)
    payload = capture(context, [rejected] + repeated() + [source('products', PRODUCTS, score=0)])
    ids = [s['evidence_id'] for s in payload['sources']]
    assert 'products' in ids
    assert 'rejected' not in ids


def test_partial_context_never_displaces_direct_support_or_becomes_complete(context):
    import evidence_graph
    import web_extract
    query = 'Qual o peso da Camera ZX com bateria e cartão?'
    context[1]['objetivo'] = query
    html = ('<main><h2>Camera ZX</h2><table>' +
            '<tr><td>Maintenance</td><td>' + 'Unrelated text. ' * 900 + '</td></tr>' +
            '<tr><th>Weight</th><td>Approx. 710 g with battery and memory card.</td></tr></table></main>')
    rec = web_extract.extrair_pagina(html, 'https://example.org/camera', query, usar_trafilatura=False)
    rec['texto_lido'] = True
    coverage = evidence_graph.requirement_coverage(query, [rec])
    assert coverage['requirements'][0]['state'] == 'PARTIALLY_SUPPORTED'
    passages = evidence_graph.select_answer_passages(coverage)
    direct = source('direct', 'Camera ZX weight is 710 g with battery and memory card.', score=0)
    items = [source(f'partial-{i}', rec['texto'], score=100-i,
                    answer_passages=passages) for i in range(6)]
    payload = capture(context, items + [direct])
    assert payload['sources'][0]['evidence_id'] == 'direct'
    assert payload['requirements'][0]['state'] == 'SUPPORTED'
    partial_only = capture(context, items)
    assert partial_only['requirements'][0]['state'] == 'PARTIALLY_SUPPORTED'


@pytest.mark.parametrize('omit_products', [False, True])
def test_complete_cited_answer_requires_review_and_survives_reload(context, omit_products):
    import research_exports
    import research_view

    db, job = context
    items = repeated() + [source('products', PRODUCTS, score=0)]
    def writer(messages, timeout):
        payload = json.loads(messages[-1]['content'])
        sources = payload['sources']
        founder = next(s for s in sources if FOUNDING in s['excerpt'])
        product = next(s for s in sources if PRODUCTS in s['excerpt'])
        return json.dumps({'points': [
            {'text': FOUNDING, 'evidence': [{'id': founder['id'], 'quote': FOUNDING}]},
            {'text': PRODUCTS, 'evidence': [{'id': product['id'], 'quote': PRODUCTS}]}]})
    writer.semantic_coverage = True

    def reviewer(messages, timeout):
        payload = json.loads(messages[-1]['content'])
        ids = {r['attribute']: r['id'] for r in payload['requirements']}
        return json.dumps({'reviews': [
            {'paragraph': 0, 'state': 'SUPPORTED', 'reason': 'none', 'answers': [
                {'requirement_id': ids['founders'], 'answer': 'Rita Silva'},
                {'requirement_id': ids['foundation_date'], 'answer': '1981'}]},
            {'paragraph': 1, 'state': 'SUPPORTED', 'reason': 'none', 'answers': [] if omit_products else [
                {'requirement_id': ids['products'], 'answer': 'motores elétricos e geradores'}]}]})

    result = ra.agente_sintetizador(db, job, items, [], writer, verificar_fn=reviewer)
    assert result['llm']
    assert result['answer_coverage']['complete'] is not omit_products
    assert result['references']['E7'] == 'products'
    assert '[E7](https://example.org/products)' in result['texto']
    assert ra.agente_auditor(db, job, result, items)['ok']
    job['sintese'], job['status'] = result, 'concluida'
    ra.salvar_job(db, job)
    ra._save_context_checkpoint(db, job)
    reloaded = ra._resumo(db, ra.carregar_job(db, job['owner'], job['id']))
    assert reloaded['sintese']['provenance'] == result['provenance']
    view = research_view.build_view(reloaded, items)
    assert PRODUCTS in view['blocks'][0]['content']
    for fmt in ('md', 'csv', 'json'):
        content, _, _ = research_exports.build_export(reloaded, items, [], fmt)
        assert PRODUCTS.encode('utf-8') in content

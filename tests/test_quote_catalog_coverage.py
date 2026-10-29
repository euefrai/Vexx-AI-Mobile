"""Catalog transport/coverage regressions; no real provider or external network."""
import json
import threading

import pytest

import research_synthesis as rs

PRODUCTS = 'Atlas fabrica motores elétricos e geradores.'
FOUNDING = 'Atlas foi fundada em 1981 por Rita Silva.'
QUERY = 'Quem fundou a Atlas, em que ano foi fundada e quais produtos fabrica?'
NOISE = ' '.join(f'Registro administrativo número {i} disponível para consulta.' for i in range(14))


def source(separate=True):
    first = FOUNDING + ' ' + NOISE
    text = first + '\n\n' + PRODUCTS
    return {'id': 'E1', 'evidence_id': 'atlas', 'title': 'Atlas', 'url': 'https://example.org/atlas',
            'excerpt': text, **({'passage_ranges': [
                {'id': 'p1', 'start': 0, 'end': len(first)},
                {'id': 'p2', 'start': len(first)+2, 'end': len(text)}]} if separate else {})}


def capture_catalog(item):
    captured = []
    def writer(messages, timeout):
        captured.append(json.loads(messages[-1]['content']))
        return '{}'
    writer.literal_quote_ids = True
    with pytest.raises(ValueError, match='synthesis schema'):
        rs.generate(QUERY, [item], [], writer)
    return captured[0]


def test_catalog_reserves_slots_for_other_passages_before_filling_first():
    options = rs.quote_options(source())
    assert any(q['text'] == PRODUCTS for q in options)
    assert options[0]['text'] == FOUNDING


def test_visible_catalog_and_requirement_states_describe_the_same_text():
    payload = capture_catalog(source(False))
    assert not any(PRODUCTS in q['text'] for q in payload['sources'][0]['quotes'])
    assert next(r for r in payload['requirements'] if r['aspect'] == 'Produtos')['state'] != 'SUPPORTED'


def test_balanced_catalog_makes_complementary_aspect_available():
    payload = capture_catalog(source())
    assert any(q['text'] == PRODUCTS for q in payload['sources'][0]['quotes'])
    assert {r['state'] for r in payload['requirements']} == {'SUPPORTED'}
    assert 'excerpt' not in payload['sources'][0]
    assert all(set(q) <= {'id', 'text', 'table_header'} for q in payload['sources'][0]['quotes'])


@pytest.mark.parametrize('item', [
    {'id': 'E1', 'evidence_id': 'empty', 'excerpt': 'Dados curtos.'},
    {'id': 'E1', 'evidence_id': 'invalid-range', 'excerpt': PRODUCTS,
     'passage_ranges': [{'start': 1, 'end': 9999}]},
])
def test_empty_or_invalid_catalog_does_not_call_model(item):
    def forbidden(*args):
        pytest.fail('must not spend an inference without citable text')
    forbidden.literal_quote_ids = True
    assert rs.generate(QUERY, [item], [], forbidden) is None


@pytest.mark.parametrize('hidden', [False, True])
def test_catalog_cannot_be_bypassed_with_raw_literal_quotes(hidden):
    item = source(False)
    quote = PRODUCTS if hidden else FOUNDING
    def writer(*args):
        return json.dumps({'points': [{'text': quote, 'evidence': [{'id': 'E1', 'quote': quote}]}]})
    writer.literal_quote_ids = True
    def review(*args):
        return json.dumps({'reviews': [{'paragraph': 0, 'state': 'SUPPORTED', 'reason': 'none'}]})
    with pytest.raises(ValueError, match='reference'):
        rs.generate(QUERY, [item], [], writer, verify_fn=review)


def test_quote_limits_literal_boundaries_and_deterministic_ids_remain():
    item = source()
    options = rs.quote_options(item)
    assert options == rs.quote_options(item)
    assert len(options) <= 12
    assert len({q['id'] for q in options}) == len(options)
    assert sum(len(q['text']) for q in options) <= 1800
    for q in options:
        assert 24 <= len(q['text']) <= 450
        assert any(q['text'] in item['excerpt'][p['start']:p['end']] for p in item['passage_ranges'])


def test_named_table_attribution_is_preserved_in_catalog_coverage():
    import evidence_graph as eg
    from test_research_completion_v5912 import article
    rec = article()
    passages = eg.select_answer_passages(eg.requirement_coverage(QUERY, [rec]))
    assert passages
    excerpt, ranges = '', []
    for p in passages:
        start = len(excerpt) + (2 if excerpt else 0)
        excerpt += ('\n\n' if excerpt else '') + p['text']
        ranges.append({**p, 'start': start, 'end': len(excerpt)})
    payload = capture_catalog({**source(), 'excerpt': excerpt, 'passage_ranges': ranges})
    assert {r['state'] for r in payload['requirements']} == {'SUPPORTED'}
    assert any(q.get('table_header') == 'Atlas Corporation' for q in payload['sources'][0]['quotes'])


@pytest.mark.parametrize('bridge,expected', [('', 'SUPPORTED'), (' Boreal assumiu.', 'DISCOVERED')])
def test_only_actually_adjacent_quotes_can_preserve_pronoun_scope(bridge, expected):
    item = {**source(False), 'excerpt': FOUNDING + bridge + ' Ela fabrica motores elétricos.'}
    payload = capture_catalog(item)
    assert next(r for r in payload['requirements'] if r['aspect'] == 'Produtos')['state'] == expected


def test_catalog_fragment_offsets_and_hash_remain_literal_after_word_splitting():
    import hashlib
    text = 'Introdução ao catálogo de equipamentos. ' + ('Registro de manutenção industrial ' * 25) + '. ' + PRODUCTS
    raw = 'Prefixo externo. ' + text
    prefix = len('Prefixo externo. ')
    digest = hashlib.sha256(raw.encode()).hexdigest()
    item = {**source(), 'excerpt': text, 'passage_ranges': [{
        'id': 'long-p', 'start': 0, 'end': len(text),
        'source_span': {'start': prefix, 'end': prefix+len(text),
                        'sha256': digest, 'scope': 'normalized_available_extraction'}}]}
    offered = rs._catalog_source(item, rs.quote_options(item, include_ranges=True))
    for p in offered['passage_ranges']:
        snippet = offered['excerpt'][p['start']:p['end']]
        span = p['source_span']
        assert raw[span['start']:span['end']] == snippet
        assert span['sha256'] == digest


def test_production_writer_flags_complete_cited_answer_reload_and_review(tmp_path, monkeypatch):
    import pc_agent
    import research_agents as ra
    import research_view
    import research_exports

    calls = []
    def generate(cfg, messages, **kwargs):
        payload = json.loads(messages[-1]['content'])
        calls.append((payload.get('task', 'write'), kwargs))
        if payload.get('task') == 'verify_support':
            ids = {r['attribute']: r['id'] for r in payload['requirements']}
            body = {'reviews': [
                {'paragraph': 0, 'state': 'SUPPORTED', 'reason': 'none', 'answers': [
                    {'requirement_id': ids['founders'], 'answer': 'Rita Silva'},
                    {'requirement_id': ids['foundation_date'], 'answer': '1981'}]},
                {'paragraph': 1, 'state': 'SUPPORTED', 'reason': 'none', 'answers': [
                    {'requirement_id': ids['products'], 'answer': 'motores elétricos e geradores'}]}]}
        else:
            quotes = payload['sources'][0]['quotes']
            ids = {text: next(q['id'] for q in quotes if q['text'] == text) for text in (FOUNDING, PRODUCTS)}
            body = {'points': [{'text': text, 'evidence': [{'id': 'E1', 'quote_id': ids[text]}]}
                               for text in (FOUNDING, PRODUCTS)]}
        return {'texto': json.dumps(body)}
    monkeypatch.setattr(pc_agent, 'gerar_texto', generate)
    db = pc_agent.open_db(tmp_path / 'catalog.sqlite')
    try:
        job = ra.criar_job(db, 'qa-catalog', QUERY, conv='qa')
        item = source()
        evidence = {'id': 'atlas', 'titulo': 'Atlas', 'dominio': 'example.org', 'url': item['url'],
                    'trecho': FOUNDING, 'texto_lido': True,
                    'answer_passages': [{**p, 'text': item['excerpt'][p['start']:p['end']]}
                                        for p in item['passage_ranges']]}
        result = ra.agente_sintetizador(db, job, [evidence], [],
                                       pc_agent._research_writer({}, threading.Event()))
        assert result['llm'] and result['answer_coverage']['complete']
        assert [phase for phase, _ in calls] == ['write', 'verify_support']
        assert all(kw['max_tokens'] == 1800 for _, kw in calls)
        assert calls[0][1]['timeout']<=25 and calls[1][1]['timeout']<=25
        assert sum(kw['timeout'] for _,kw in calls)<=50
        assert '[E1](https://example.org/atlas)' in result['texto']
        assert [p['quote'] for p in result['provenance']] == [FOUNDING, PRODUCTS]
        job['sintese'], job['status'] = result, 'concluida'
        ra.salvar_job(db, job)
        ra._save_context_checkpoint(db, job)
        loaded = ra._resumo(db, ra.carregar_job(db, job['owner'], job['id']))
        assert loaded['sintese']['provenance'] == result['provenance']
        assert PRODUCTS in research_view.build_view(loaded, [evidence])['blocks'][0]['content']
        cards=next(b['props']['items'] for b in research_view.build_view(loaded,[evidence])['blocks'] if b.get('component')=='sources')
        assert cards[0]['status']=='utilizada'
        for fmt in ('md', 'csv', 'json'):
            exported, _, _ = research_exports.build_export(loaded, [evidence], [], fmt)
            assert PRODUCTS.encode('utf-8') in exported
    finally:
        db.close()

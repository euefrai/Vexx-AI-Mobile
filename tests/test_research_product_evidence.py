"""Read structured offers survive research without accepting index-only prices."""
import copy
import json
import re

import pytest

import pc_agent
import public_store_reader
import research_agents as agents
import research_product_evidence as product_evidence
import research_view
import research_synthesis
from test_shopping_v55 import PAGINA_PRODUTO

URL = 'https://loja.com/produto/x'
QUERY = 'Notebook Gamer X 16GB RAM preco'


def extract(page=PAGINA_PRODUTO):
    return product_evidence.extract(page, URL, 'Notebook Gamer X 16GB RAM', QUERY)


def test_observed_offer_preserves_explicit_fields_without_network(monkeypatch):
    monkeypatch.setattr(public_store_reader, 'fetch', lambda *a, **kw: pytest.fail('HTML was already read'))
    offer = extract()
    assert offer['price'] == 4299 and offer['currency'] == 'BRL'
    assert offer['availability'] == 'em_estoque'
    assert offer['fields']['price'] == '4299.00'
    assert offer['field_path'] == 'Product.offers'
    assert 'R$ 4.299,00' in product_evidence.text(offer, URL)
    assert offer['observed_at'] in product_evidence.text(offer, URL)
    assert product_evidence.valid(offer, URL)


@pytest.mark.parametrize('change', ['missing_currency', 'expired', 'other_item', 'aggregate',
                                 'range', 'invalid_price', 'wrong_product'])
def test_incomplete_or_mismatched_offer_is_not_promoted(change):
    match = re.search(r'<script[^>]+>(.*?)</script>', PAGINA_PRODUTO)
    data = json.loads(match[1])
    offer = data['offers']
    if change == 'missing_currency': offer.pop('priceCurrency')
    elif change == 'expired': offer['priceValidUntil'] = '2000-01-01'
    elif change == 'other_item': offer['url'] = 'https://loja.com/produto/another'
    elif change == 'aggregate': offer['@type'] = 'AggregateOffer'
    elif change == 'range': data['offers'] = [offer, dict(offer, price='4999.00')]
    elif change == 'invalid_price': offer['price'] = '-10'
    elif change == 'wrong_product': data['name'] = 'Geladeira 400L'
    page = PAGINA_PRODUTO[:match.start(1)] + json.dumps(data) + PAGINA_PRODUTO[match.end(1):]
    assert extract(page) is None


def test_challenge_with_product_schema_has_no_observed_offer():
    assert extract('<h1>Verify you are human</h1>' + PAGINA_PRODUTO) is None


@pytest.mark.parametrize('change', ['price', 'currency', 'availability', 'fields', 'url',
                                  'timestamp', 'naive_timestamp', 'field_path'])
def test_modified_record_cannot_produce_card_or_synthesis_fact(change):
    offer = copy.deepcopy(extract())
    if change == 'price': offer['price'] = 1
    elif change == 'currency': offer['currency'] = 'USD'
    elif change == 'availability': offer['availability'] = 'sem_estoque'
    elif change == 'fields': offer['fields']['name'] = 'Another product'
    elif change == 'url': offer['url'] = 'https://loja.com/produto/another'
    elif change == 'timestamp': offer['observed_at'] = 'yesterday'
    elif change == 'naive_timestamp': offer['observed_at'] = '2026-11-03T08:00:00'
    elif change == 'field_path': offer['field_path'] = 'Search.snippet'
    assert not product_evidence.valid(offer, URL)
    assert product_evidence.text(offer, URL) == ''


def test_price_reaches_persisted_evidence_context_and_card(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / 'product.sqlite')
    monkeypatch.setattr(public_store_reader, 'fetch', lambda *a, **kw: (URL, PAGINA_PRODUTO))
    try:
        job = agents.criar_job(db, 'qa', QUERY)
        results = agents.agente_analista(db, job, {'id': 'read', 'alvo': QUERY},
            [{'url': URL, 'titulo': 'Notebook Gamer X 16GB RAM', 'trecho': 'Notebook'}])
        assert len(results) == 1
        saved = agents.listar_evidencias(db, 'qa', job['id'])
        assert saved[0]['product_offer']['price'] == 4299
        _, sources = agents._synthesis_context(QUERY, saved, {saved[0]['id']: 'E1'})
        assert sources[0]['scope'] == 'structured_product_offer'
        assert 'R$ 4.299,00' in sources[0]['excerpt']
        assert sources[0]['structured_provenance']['sha256'] == saved[0]['product_offer']['sha256']
        card = research_view.source_card(saved[0])
        assert any('R$ 4.299,00' in text for text in card['detalhes'])
        assert card['tipo'] == 'Oferta' and 'R$ 4.299,00' in card['trecho']
        assert card['url'] == URL
        def failed_writer(*args):
            raise TimeoutError('unavailable model')
        result = agents.agente_sintetizador(db, job, saved, [], sintetizar_fn=failed_writer)
        assert not result['llm']
        assert 'R$ 4.299,00' in result['texto'] and URL in result['texto']
        assert 'Consultado em ' in result['texto'] and ' UTC.' in result['texto']
        quotes = research_synthesis.quote_options(sources[0])
        assert len(quotes) == 1
        assert quotes[0]['text'] == sources[0]['excerpt']
        for value in ('Notebook Gamer X', 'R$ 4.299,00', 'em estoque', saved[0]['product_offer']['observed_at']):
            assert value in quotes[0]['text']
    finally:
        db.close()


def test_offer_does_not_replace_other_answer_passages_or_shift_source_offsets():
    passage = 'Notebook Gamer X 16GB RAM tem peso de 2 kg com bateria instalada.'
    item = {'id':'ev1', 'url':URL, 'titulo':'Notebook Gamer X 16GB RAM', 'dominio':'loja.com',
            'trecho':passage, 'texto':passage, 'texto_lido':True, 'access_state':'read',
            'content_scope':'page_text', 'product_offer':extract(),
            'answer_passages':[{'id':'p1', 'text':passage, 'text_span':{'start':0,'end':len(passage)},
                                'source_span':{'start':120,'end':120+len(passage),'sha256':'a'*64}}]}
    _, sources = agents._synthesis_context('Notebook Gamer X 16GB RAM peso e preco', [item], {'ev1':'E1'})
    source = sources[0]
    assert len(source['excerpt']) <= 1800 and passage in source['excerpt']
    assert 'R$ 4.299,00' in source['excerpt']
    span = source['passage_ranges'][1]
    assert source['excerpt'][span['start']:span['end']] == passage
    assert span['source_span'] == item['answer_passages'][0]['source_span']
    quotes = research_synthesis.quote_options(source, include_ranges=True)
    assert any(q['text'] == passage for q in quotes)
    assert any('R$ 4.299,00' in q['text'] and 'Notebook Gamer X' in q['text'] for q in quotes)

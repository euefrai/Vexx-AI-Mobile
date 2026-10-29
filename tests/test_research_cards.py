"""Presentation must retain answer passages and the sources actually cited."""
import threading

import pytest

import pc_agent
import research
import research_view


def source(**changes):
    return dict(id='late', titulo='Documento', url='https://example.org/document',
                trecho='Introdução sem a resposta.', texto_lido=True, **changes)


def test_card_shows_selected_answer_passage_instead_of_page_lead():
    record = source(answer_passages=[None, {'text': 'A garantia cobre três anos.',
                                          'section': 'Garantia'}])
    card = research_view.source_card(record, used=True)
    assert card['trecho'] == 'A garantia cobre três anos.'
    assert 'Introdução' not in card['trecho']
    assert 'Contexto da seção: Garantia' in card['detalhes']
    assert card['status'] == 'utilizada'


def test_unread_record_does_not_promote_stale_full_text_metadata():
    record = source(answer_passages=[{'text': 'Dado de leitura anterior.'}],
                    status='encontrada', full_text_fetched=True, access_state='blocked')
    card = research_view.source_card(record, used=True)
    assert card['trecho'] == 'Introdução sem a resposta.'
    assert card['leitura'] == 'UNAVAILABLE'
    assert card['status'] == 'encontrada'
    assert card['escopo'] == 'Página não lida; sem suporte factual'


def test_abstract_passage_keeps_partial_scope():
    card = research_view.source_card(source(content_scope='abstract_only',
        abstract='Resumo recuperado.', answer_passages=[{'text': 'Resultado do resumo.'}]))
    assert card['trecho'] == 'Resultado do resumo.'
    assert card['leitura'] == 'PARTIAL'
    assert 'texto completo não lido' in card['escopo']


def test_cited_late_source_survives_the_ten_card_limit_without_mutation():
    discovered = [dict(id=str(i), titulo=f'Prévia {i}',
        url=f'https://example.org/{i}', status='encontrada', trecho='Prévia') for i in range(11)]
    used = source()
    records = discovered + [used]
    original = list(records)
    view = research_view.build_view({'objetivo': 'Garantia', 'achados': [
        {'afirmacao': 'Três anos.', 'estado': 'UNVERIFIED', 'supporting_ids': ['late']}]}, records)
    cards = next(b['props']['items'] for b in view['blocks'] if b.get('component') == 'sources')
    assert len(cards) == 10
    assert cards[0]['url'] == used['url']
    assert cards[0]['status'] == 'utilizada'
    assert cards[1]['url'] == discovered[0]['url']
    assert records == original


def test_read_context_sources_rank_before_unread_discovery():
    records = [dict(id=str(i), titulo=f'Prévia {i}', url=f'https://example.org/{i}',
                    status='encontrada') for i in range(11)] + [source()]
    view = research_view.build_view({'objetivo': 'Contexto'}, records)
    cards = next(b['props']['items'] for b in view['blocks'] if b.get('component') == 'sources')
    assert cards[0]['url'] == 'https://example.org/document'


def test_explicit_read_list_is_bounded_and_ignores_urls_in_quoted_metadata():
    urls = [f'https://example.org/{i}' for i in range(9)]
    request = 'Compare estas fontes:\n' + '\n'.join([urls[0]] + urls) + '\n\nTítulo: https://unrequested.example/'
    assert research.urls_pedidas(request) == urls[:6]
    assert research.urls_pedidas('Analise esta fonte:\n' + urls[0] + '\n\nExplique as limitações.') == urls[:1]
    assert research.urls_pedidas('achei essa referência em ' + urls[0]
        + ' ontem, mas minha pergunta agora é sobre outro assunto: energia solar.') == []
    assert research.urls_pedidas('pesquise energia e veja ' + urls[0]) == []
    assert research.urls_pedidas('Compare estas fontes:\nnão é um link\n' + urls[0]) == []


def test_reader_is_concurrent_bounded_and_preserves_request_order(monkeypatch):
    gate = threading.Barrier(3)
    lock = threading.Lock()
    counts = {'active': 0, 'peak': 0}
    urls = [f'https://example.org/{i}' for i in range(8)]

    def read(url, consulta='', timeout=8):
        assert 0 < timeout <= 8
        with lock:
            counts['active'] += 1
            counts['peak'] = max(counts['peak'], counts['active'])
        try:
            gate.wait(timeout=4)
            if url.endswith('/2'):
                raise RuntimeError('Controlled network failure')
            return {'url': url}, ''
        finally:
            with lock:
                counts['active'] -= 1

    monkeypatch.setattr(research, 'analisar_url', read)
    results = research.analisar_urls(urls)
    assert [r[0] for r in results] == urls[:6]
    assert counts['peak'] == 3
    assert results[2][1:] == (None, 'rede')
    assert results[-1][1]['url'] == urls[5]


def test_reader_does_not_start_pages_after_shared_budget_expires(monkeypatch):
    ticks = iter([0.0, 20.0, 20.0])
    monkeypatch.setattr(research.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(research, 'analisar_url', lambda *a, **k: pytest.fail('Expired request must not start'))
    assert research.analisar_urls(['https://example.org/a']) == [('https://example.org/a', None, 'timeout')]


def test_comparison_sends_each_read_page_to_model_context_and_keeps_failure(monkeypatch, tmp_path):
    db = pc_agent.open_db(tmp_path / 'comparison.sqlite')
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 'BASE',
           'context': 12, 'max_tokens': 500, 'pesquisa_web': True}
    urls = ['https://example.org/a', 'https://example.net/b', 'https://example.com/blocked']

    def download(url, **kwargs):
        if url == urls[2]:
            raise research.ResearchErro('Blocked', 'bloqueado')
        marker = 'GARANTIA-TRES-ANOS' if url == urls[0] else 'GARANTIA-DOIS-ANOS'
        html = '<html><head><title>Garantia</title></head><body><article><p>' + (marker + ' Condições de uso. ') * 20 + '</p></article></body></html>'
        return url, html

    monkeypatch.setattr(research, 'baixar', download)
    monkeypatch.setattr(research, '_ips_globais', lambda host: None)
    for name in ('pesquisa_rapida', 'pesquisa_aprofundada'):
        monkeypatch.setattr(research, name, lambda *a, **k: pytest.fail('Explicit URLs must not be replaced by generic search'))
    try:
        messages, extras = pc_agent.ai_montar_mensagens(db, 'qa-comparison', cfg,
            'Compare estas fontes:\n' + '\n'.join(urls) + '\n\nCite as diferenças e limitações.')
        system = messages[0]['content']
        assert 'GARANTIA-TRES-ANOS' in system and 'GARANTIA-DOIS-ANOS' in system
        assert urls[2] in system and 'não pôde ser lida' in system
        assert [f['id'] for f in extras['fontes']] == ['S1', 'S2']
        assert [f['url'] for f in extras['fontes']] == urls[:2]
        assert extras['paginas_usuario'] == urls
    finally:
        db.close()


def test_explicit_reader_uses_the_existing_private_address_rejection():
    result = research.analisar_urls(['http://127.0.0.1/private'])
    assert result[0][1] is None
    assert result[0][2] == 'ssrf'


@pytest.mark.parametrize('web,restriction', [(False, ''), (True, '\n\nNão pesquise na internet.')])
def test_requested_pages_respect_disabled_web_and_user_restrictions(monkeypatch, tmp_path, web, restriction):
    db = pc_agent.open_db(tmp_path / 'restricted.sqlite')
    monkeypatch.setattr(research, 'analisar_urls', lambda *a, **k: pytest.fail('Web reading is disabled'))
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 'BASE',
           'context': 12, 'max_tokens': 500, 'pesquisa_web': web}
    try:
        _, extras = pc_agent.ai_montar_mensagens(db, 'qa-restricted', cfg,
            'Compare estas fontes:\nhttps://example.org/a\nhttps://example.net/b' + restriction)
        assert not extras.get('paginas_usuario')
        assert not extras.get('fontes')
    finally:
        db.close()

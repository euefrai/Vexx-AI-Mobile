"""Acceptance regressions from the 2026-11-05 operational audit.

Collected by the regular suite; no credentials, real databases, native input,
external HTTP, xfail, or skipped checks.
"""
from datetime import datetime, timezone
import time
import sqlite3

import pytest

import live_data
from pc_companion.indexer import FileIndex


def test_native_longcat_tool_call_is_filtered_without_execution():
    import tool_protocol
    raw = ('<longcat_tool_call>browser_navigate\n'
           '<longcat_arg_key>url</longcat_arg_key>\n'
           '<longcat_arg_value>https://www.sqlite.org/wal.html</longcat_arg_value>\n'
           '</longcat_tool_call>')
    clean, errors = tool_protocol.sanitizar_texto(raw)
    sanitizer = tool_protocol.Sanitizador()
    parts = [sanitizer.alimentar(raw[i:i+3]) for i in range(0, len(raw), 3)]
    end, stream_errors = sanitizer.finalizar()
    streamed = ''.join(parts) + end
    assert not clean.strip() and errors
    assert not streamed.strip() and stream_errors


def test_known_document_keeps_passage_answering_the_named_error():
    """A public SQLite read reached the page, but discarded its busy passage."""
    import research
    intro = ('SQLite WAL and rollback journal overview. Readers and writers '
             'can use database transactions. ' * 50)
    answer = ('If another database connection holds an exclusive lock, '
              'a WAL query can return SQLITE_BUSY.')
    text = intro + '\n\nSometimes Queries Return SQLITE_BUSY In WAL Mode\n\n' + answer
    url = 'https://www.sqlite.org/wal.html'
    source = research._fonte_de({
        'titulo': 'Write-Ahead Logging', 'texto': text, 'trecho_usado': intro[:400],
        'final': url, 'metadados': {}, 'lida': True,
    }, {'url': url, 'trecho': ''}, 'When can WAL return SQLITE_BUSY?',
        avaliar_relevancia=False)
    assert answer in source['texto_lido']


def test_question_about_document_deadline_is_not_a_personal_memory():
    import pc_agent
    question = ('Leia o documento anexado. Qual é o orçamento, quantos sensores '
                'e qual é o prazo do Projeto Órbita? Use apenas o documento.')
    assert pc_agent.extrair_candidatos(question) == []


def test_document_budget_does_not_get_a_shopping_disclaimer():
    import pc_agent
    answer = ('Com base apenas no documento anexado, o Projeto Órbita possui:\n'
              '| Item | Valor |\n| Orçamento | R$ 1.200,00 |\n'
              '| Quantidade de sensores | 12 |\n| Prazo | 20/11/2026 |\n'
              'Observação: o documento indica que ele é um arquivo sintético '
              'e não contém dados reais.')
    result = pc_agent._validar_resposta({'intencao': 'conversa', 'ferramentas': []},
        answer, usadas=['docs'], produtos=[], mid='audit-document')
    assert 'confirme na loja antes de comprar' not in result
    assert result == answer


def test_failed_product_refresh_preserves_displayed_context(monkeypatch):
    import conversation_followups
    import shopping
    with sqlite3.connect(':memory:') as db:
        shopping.criar_tabelas(db)
        products = [{'id': 'fixture-a', 'nome': 'Galaxy A15', 'modelo': 'A15'},
                    {'id': 'fixture-b', 'nome': 'Galaxy A16', 'modelo': 'A16'}]
        criteria = shopping.extrair_criterios('Celular Samsung até R$ 1000')
        shopping.salvar_consulta(db, 'audit-owner', 'audit-conv', 'celular Samsung',
                                 criteria, {'produtos': products, 'criterios': criteria})
        monkeypatch.setattr(shopping, 'pesquisar', lambda *args, **kwargs: {
            'produtos': [], 'criterios': criteria, 'fontes': []})
        conversation_followups.product_reply(db, 'audit-owner', 'audit-conv',
            'Compare Galaxy A15 com as outras opções', 'Galaxy A15 e Galaxy A16')
        latest = shopping.ultima_consulta(db, 'audit-owner', 'audit-conv')
        assert latest['resultado']['produtos'] == products


def test_chat_model_catalog_does_not_offer_embeddings(monkeypatch):
    import providers
    monkeypatch.setattr(providers, 'chave', lambda name: 'fixture-only' if name == 'gemini' else '')
    monkeypatch.setattr(providers, 'chave_origem', lambda _: '')
    monkeypatch.setattr(providers.hermes_bridge, 'listar_modelos', lambda *a, **kw: [])
    # The catalog has model IDs but discards capability information.
    monkeypatch.setattr(providers, '_modelos_vivos_openai', lambda *a, **kw: (
        ['models/gemini-embedding-001', 'models/gemini-2.5-flash'], ''))
    catalog = providers.listar_tudo()
    ids = set(catalog['models'])
    assert 'gemini/models/gemini-2.5-flash' in ids
    assert 'gemini/models/gemini-embedding-001' not in ids


def make_index(tmp_path):
    root = tmp_path / 'documents'
    root.mkdir()
    index = FileIndex(tmp_path / 'index.sqlite', [root])
    deadline = time.monotonic() + 3
    while index.migrating and time.monotonic() < deadline:
        time.sleep(.005)
    assert not index.migrating
    return index, root


def test_brasilia_clock_without_weather_credentials(monkeypatch):
    """A clock question about the national reference must not require weather."""
    monkeypatch.setattr(live_data, 'geocode', lambda _: (
        {'label': 'Brasília, Distrito Federal, Brasil', 'latitude': -15.7939,
         'longitude': -47.8828, 'ibge_id': '5300108'}, None))
    def unavailable(*args, **kwargs):
        raise live_data.WeatherError('missing_key')
    monkeypatch.setattr(live_data, '_weather_data', unavailable)
    answer = live_data.clock('Que horas são em Brasília?', {},
                             datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc))
    assert '15:00' in answer and '05/11/2026' in answer


def test_file_search_finds_part_of_parent_path(tmp_path):
    """The UI promises names, extensions, and parts of the path."""
    index, root = make_index(tmp_path)
    try:
        parent = root / 'relatorios_orbitais'
        parent.mkdir()
        target = parent / 'manual.txt'
        target.write_text('synthetic audit file', encoding='utf-8')
        index.scan()
        result = index.search('relatorios_orbitais', kind='files')
        assert str(target) in {row['path'] for row in result['items']}
    finally:
        index.stop.set()


def test_missing_fts_table_is_not_reported_as_timeout(tmp_path):
    """A damaged/missing index needs a distinct diagnosis, not a fake timeout."""
    index, _ = make_index(tmp_path)
    try:
        with index.db() as db:
            db.execute('DROP TABLE names')
            db.commit()
        result = index.search('manual')
        assert 'limite de tempo' not in result.get('hint', '')
        assert result.get('error') or result.get('code')
    finally:
        index.stop.set()


def test_filename_search_still_works_with_accents_and_quotes(tmp_path):
    index, root = make_index(tmp_path)
    try:
        target = root / 'relatório órbita.txt'
        target.write_text('synthetic', encoding='utf-8')
        index.scan()
        assert str(target) in {row['path'] for row in index.search('relatório')['items']}
        # A quote is data, never an FTS operator or SQL instruction.
        result = index.search('" OR manual')
        assert not result['items']
    finally:
        index.stop.set()


@pytest.mark.parametrize('city,expected', [('UTC','18:00'), ('America/Bahia','15:00')])
def test_explicit_iana_clock_never_needs_weather(monkeypatch, city, expected):
    monkeypatch.setattr(live_data, '_weather_data', lambda *a: pytest.fail('Weather called'))
    answer = live_data.clock('Que horas são em ' + city + '?', {},
                             datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc))
    assert expected in answer

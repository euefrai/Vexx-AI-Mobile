"""Regressions for real retrieval failures; fixtures never represent live offers."""
import copy
import json
import sqlite3
from datetime import datetime, timezone

import docs_agent
import search_orchestrator as orch
import search_providers as providers
import research
import shopping
import pytest


def test_fallback_is_sorted_even_with_fts_installed():
    db = sqlite3.connect(':memory:')
    docs_agent.criar_tabelas(db)
    for name, content in [('weak.txt', 'banana orchard note'), ('strong.txt', 'banana tropical fruit')]:
        docs_agent.salvar_documento(db, name, content.encode(), 'test', owner='qa')
    hits = docs_agent.trechos_relevantes(db, 'banana tropical fruit yellow', owner='qa')
    assert hits[0]['doc'] == 'strong.txt'


def test_temporal_intent_reaches_document_retrieval():
    db = sqlite3.connect(':memory:')
    docs_agent.criar_tabelas(db)
    for name, text in [('old.txt', 'Report 2023. Average chamber humidity was 60 percent during the trial.'),
                       ('new.txt', 'Report 2025. Average chamber humidity was 45 percent after the retrofit.'),
                       ('decoy.txt', 'Report 2026. Fruit harvest banana.')]:
        docs_agent.salvar_documento(db, name, text.encode(), 'test', owner='qa')
    hits = docs_agent.trechos_relevantes(db, 'average chamber humidity trial', owner='qa',
                                        contexto='Qual a umidade atual da câmara?')
    assert hits[0]['doc'] == 'new.txt'
    assert 'old.txt' in [h['doc'] for h in hits]
    assert 'decoy.txt' not in [h['doc'] for h in hits]
    assert docs_agent.trechos_relevantes(db, 'average chamber humidity trial', owner='qa')[0]['doc'] == 'old.txt'


def test_publication_date_is_not_indexing_or_update_date():
    assert orch._data_do_item({'indexed_at': '2026-10-01', 'fetched_at': '2026-10-01'}) is None
    assert orch._data_do_item({'updated_at': '2026-10-01'}) is None
    dt = orch._data_do_item({'publicado_em': '2024-03-01T01:00:00+03:00'})
    assert dt.isoformat() == '2024-02-29T22:00:00+00:00'
    for raw in ('2025-02-30', 'garbage', '2999-01-01'):
        assert orch._data_do_item({'publicado_em': raw}) is None


def test_temporal_ranking_uses_publication_only_and_keeps_relevance_first():
    year = datetime.now(timezone.utc).year
    hits = [
        {'titulo': 'Baterias estado sólido', 'publicado_em': '2018-01-01', 'indexed_at': f'{year}-01-01', 'url': 'https://a.test/old'},
        {'titulo': 'Baterias estado sólido', 'publicado_em': f'{year-1}-01-01', 'url': 'https://a.test/new'},
        {'titulo': 'Baterias estado sólido', 'url': 'https://a.test/unknown'},
        {'titulo': 'Frutas', 'publicado_em': f'{year}-01-01', 'fonte_primaria': True, 'url': 'https://a.test/decoy'},
    ]
    query = 'Baterias estado sólido recentes'
    info = orch.classificar(query)
    ranked = orch.ranquear(copy.deepcopy(hits), query, info['classes'], info)
    assert ranked[0]['url'].endswith('/new')
    assert ranked[-1]['url'].endswith('/decoy')
    assert 'ano' not in next(a for a in ranked if a['url'].endswith('/unknown'))
    plain = 'Baterias estado sólido'
    info = orch.classificar(plain)
    old, new = copy.deepcopy(hits[:2])
    assert orch._pontos_relevancia(old, plain, info['classes'], info) == orch._pontos_relevancia(new, plain, info['classes'], info)


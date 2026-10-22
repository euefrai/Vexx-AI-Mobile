"""Deterministic local research pipeline; no external claims or paid inference."""
import json
import pc_agent
import research_agents as ra


def _job(tmp_path, objective='Baterias de estado sólido desde 2024'):
    db = pc_agent.open_db(tmp_path / 'research.sqlite')
    job = ra.criar_job(db, 'qa', objective, manual='profunda')
    ra.montar_plano(db, job)
    return db, job


def test_replan_invalidates_derived_results_and_keeps_completed_readings(tmp_path):
    db, job = _job(tmp_path)
    for step in job['plano']:
        step.update(status='feita', _sintese={'texto': 'old'})
    original = [s['id'] for s in job['plano'] if s['tipo'] == 'ler']
    ra.replanejar(db, job, ['baterias estado sólido desde 2024 metodologia'])
    for step in job['plano']:
        if step['tipo'] in ('verificar', 'sintetizar', 'auditar'):
            assert step['status'] == 'pendente' and '_sintese' not in step
        if step['id'] in original:
            assert step['status'] == 'feita'
    checker = next(s for s in job['plano'] if s['tipo'] == 'verificar')
    assert len(checker['dependencias']) == len([s for s in job['plano'] if s['tipo'] == 'analisar'])


def test_gap_query_keeps_original_subject_constraints(tmp_path):
    db, job = _job(tmp_path, 'Galaxy A56 256 GB até R$ 3000')
    for step in job['plano']:
        step['status'] = 'feita'
    gap = ra._lacunas(job)[0]
    assert all(token in gap for token in ('Galaxy', 'A56', '256', '3000'))
    ra.replanejar(db, job, [gap] * 20)
    added = [s for s in job['plano'] if s.get('replan_reason') and s['tipo'] == 'busca']
    assert len(added) == 1


def test_search_does_not_drop_short_models_or_overrun_remaining_budget(tmp_path):
    db, job = _job(tmp_path, 'Quanto custa Galaxy A56 256 GB até R$ 3000?')
    job['orcamento']['buscas'] = 1
    class Empty:
        nome = 'fixture'
        queries = []
        def buscar(self, query, limite=6):
            self.queries.append(query)
            return []
    provider = Empty()
    step = next(s for s in job['plano'] if s['tipo'] == 'busca')
    ra.agente_busca(db, job, step, [provider], set())
    assert len(provider.queries) == 1 and job['usados']['buscas'] == 1
    assert 'A56' in provider.queries[0] and '256' in provider.queries[0]


def test_adaptive_pipeline_synthesis_contains_new_round_evidence(tmp_path):
    db, job = _job(tmp_path, 'Bateria ZX capacidade nominal')
    job['orcamento'].update(buscas=4, paginas=4, subs=1, replans=1)
    ra.salvar_job(db, job)
    class Provider:
        nome = 'fixture'
        def buscar(self, query, limite=6):
            return [{'titulo': 'Bateria ZX', 'url': 'https://example.com/primary',
                     'trecho': 'Bateria ZX capacidade nominal de 500 ciclos.'}] if 'fontes primárias' in query else []
    out = ra.executar(db, job['id'], 'qa', [Provider()],
        recuperar_fn=lambda u: {'titulo': 'Bateria ZX', 'texto': 'Bateria ZX capacidade nominal de 500 ciclos.', 'final': u})
    current = ra.carregar_job(db, 'qa', job['id'])
    assert current['usados']['replans'] == 1
    assert '500 ciclos' in out.get('sintese', {}).get('texto', '')
    assert '500 ciclos' in ra._resumo(db, current)['sintese']['texto']
    assert any(e['tipo'] == 'adaptive_round_evaluated' for e in ra.eventos_desde(db, 'qa', job['id']))
    assert ra.listar_evidencias(db, 'another-owner', job['id']) == []


def test_explicitly_unread_snippet_cannot_support_a_fact(tmp_path):
    db, job = _job(tmp_path, 'A bateria tem 500 ciclos de vida útil?')
    evidence = {'id': 'e1', 'url': 'https://example.com/source', 'titulo': 'Bateria',
                'dominio': 'example.com', 'trecho': 'A bateria tem 500 ciclos de vida útil.',
                'texto_lido': False, 'access_state': 'snippet_only'}
    verdicts = ra.agente_verificador(db, job, [evidence])
    assert all(v['estado'] not in ('SUPPORTED', 'PARTIALLY_SUPPORTED', 'CONTRADICTED') for v in verdicts)
    assert all(not v['supporting_ids'] and not v['contradicting_ids'] for v in verdicts)

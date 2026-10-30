"""Read discovered complementary aspects with real persistence, no network/model."""
import threading

import pytest

import evidence_graph as eg
import research_agents as ra
from test_research_parallel_reading import research_job


QUESTION = 'Quem fundou a Luma, em que ano e quais produtos fabrica?'
FOUNDING = 'A Luma foi fundada em 1902 por Ana Ribeiro.'
PRODUCTS = 'A Luma fabrica motores e geradores.'


def candidate(name, title='Luma empresa'):
    return {'id': name, 'titulo': title, 'url': 'https://audit.example/' + name,
            'trecho': title}


def run_reader(db, job, rows, texts, *, teto_paginas=3, **kwargs):
    called = []

    def read(url):
        name = url.rsplit('/', 1)[-1]
        called.append(name)
        return {'titulo': 'Luma empresa', 'texto': texts[name],
                'texto_lido': True, 'final': url}

    evidence = ra.agente_analista(db, job, {'id': 'aspect-read', 'alvo': job['objetivo']},
                                rows, read, teto_paginas=teto_paginas, **kwargs)
    return evidence, called


def test_repeated_partial_sources_do_not_hide_discovered_complement(research_job):
    db, job = research_job
    job['objetivo'] = QUESTION
    job['orcamento']['paginas'] = 6
    rows = [candidate(str(i)) for i in range(4)]
    evidence, called = run_reader(db, job, rows,
        {'0': FOUNDING, '1': FOUNDING, '2': FOUNDING, '3': PRODUCTS})
    assert set(called) == {'0', '1', '2', '3'}
    assert job['usados']['paginas'] == 4
    assert eg.requirement_coverage(QUESTION, evidence)['complete']
    persisted = ra.listar_evidencias(db, job['owner'], job['id'])
    assert eg.requirement_coverage(QUESTION, persisted)['complete']
    assert any(e['trecho'] == FOUNDING for e in persisted)
    assert any(e['tipo'] == 'source_aspect_read_started'
               for e in ra.eventos_desde(db, job['owner'], job['id']))


def test_metadata_prioritizes_complement_without_replacing_read_evidence(research_job):
    db, job = research_job
    job['objetivo'] = QUESTION
    rows = [candidate('first'), candidate('repeat'), candidate('products', 'Produtos da Luma')]
    evidence, called = run_reader(db, job, rows,
        {'first': FOUNDING, 'repeat': FOUNDING, 'products': PRODUCTS}, teto_paginas=1)
    assert called == ['first', 'products']
    assert eg.requirement_coverage(QUESTION, evidence)['complete']


@pytest.mark.parametrize('question,first,complement', [
    (QUESTION, FOUNDING, PRODUCTS),
    ('Quais foram as causas e consequências da Revolta Aurora?',
     'A Revolta Aurora foi motivada pelos castigos físicos impostos aos marinheiros.',
     'A Revolta Aurora resultou na aprovação de novas regras para os marinheiros.'),
])
def test_unseen_multi_aspect_question_uses_actual_read_passages(research_job, question, first, complement):
    db, job = research_job
    job['objetivo'] = question
    rows = [candidate('first', question), candidate('second', question)]
    evidence, called = run_reader(db, job, rows,
        {'first': first, 'second': complement}, teto_paginas=1)
    assert called == ['first', 'second']
    assert eg.requirement_coverage(question, evidence)['complete']


def test_complete_read_does_not_spend_more_pages(research_job):
    db, job = research_job
    job['objetivo'] = QUESTION
    evidence, called = run_reader(db, job, [candidate('first'), candidate('unused')],
        {'first': FOUNDING + ' ' + PRODUCTS}, teto_paginas=1)
    assert called == ['first'] and job['usados']['paginas'] == 1
    assert eg.requirement_coverage(QUESTION, evidence)['complete']


def test_previously_persisted_aspects_are_counted_before_more_reading(research_job):
    db, job = research_job
    job['objetivo'] = QUESTION
    first, _ = run_reader(db, job, [candidate('complete')],
                         {'complete': FOUNDING + ' ' + PRODUCTS}, teto_paginas=1)
    assert eg.requirement_coverage(QUESTION, first)['complete']
    evidence, called = run_reader(db, job, [candidate('new'), candidate('unused')],
                                 {'new': FOUNDING}, teto_paginas=1)
    assert called == ['new'] and job['usados']['paginas'] == 2
    assert evidence[0]['trecho'] == FOUNDING


@pytest.mark.parametrize('remaining', [1, 5])
def test_existing_page_and_attempt_limits_still_cap_partial_reads(research_job, remaining):
    db, job = research_job
    job['objetivo'] = QUESTION
    job['orcamento']['paginas'] = remaining
    rows = [candidate(str(i)) for i in range(4)]
    evidence, called = run_reader(db, job, rows, {str(i): FOUNDING for i in range(4)},
                                teto_paginas=1)
    assert len(called) == min(remaining, 2)
    assert job['usados']['paginas'] == len(called)
    assert not eg.requirement_coverage(QUESTION, evidence)['complete']


def test_wrong_entity_metadata_cannot_fill_missing_aspect(research_job):
    db, job = research_job
    job['objetivo'] = QUESTION
    rows = [candidate('first'), candidate('wrong', 'Produtos da Luma')]
    evidence, called = run_reader(db, job, rows,
        {'first': FOUNDING, 'wrong': 'A Outra fabrica motores e geradores.'}, teto_paginas=1)
    assert called == ['first', 'wrong']
    assert [e['trecho'] for e in evidence] == [FOUNDING]
    coverage = eg.requirement_coverage(QUESTION, evidence)
    assert next(r for r in coverage['requirements'] if r['attribute'] == 'products')['state'] != 'SUPPORTED'


def test_cancelled_reader_does_not_start_complement(research_job):
    db, job = research_job
    job['objetivo'] = QUESTION
    cancel = threading.Event()
    called = []

    def read(url):
        called.append(url)
        cancel.set()
        return {'titulo': 'Luma empresa', 'texto': FOUNDING, 'texto_lido': True, 'final': url}

    ra.agente_analista(db, job, {'id': 'aspect-cancel', 'alvo': QUESTION},
        [candidate('first'), candidate('unused')], read,
        teto_paginas=1, deve_parar=cancel.is_set)
    assert len(called) == 1 and job['usados']['paginas'] == 1

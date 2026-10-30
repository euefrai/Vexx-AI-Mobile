"""Regressions for natural retrieval requests; all documents below are fixtures."""
import pytest

import evidence_graph as eg
import query_intelligence as qi
import search_orchestrator as orch


TIMEOUT = ('Pesquise na documentação oficial de Python o que faz asyncio.timeout '
           'e o que acontece quando o prazo expira.')
COMPARISON = ('Pesquise a diferença entre memória RAM e SSD e como cada um afeta '
              'o desempenho do computador.')
STOICISM = ('Pesquise o que é estoicismo e explique a distinção entre o que depende '
           'de nós e o que não depende.')


@pytest.mark.parametrize('query,entities,facet', [
    (TIMEOUT, {'asyncio.timeout'}, 'behavior'),
    (COMPARISON, {'memória RAM', 'SSD'}, 'definition'),
    (STOICISM, {'estoicismo'}, 'definition'),
    ('Busque o que faz pathlib.Path.resolve e quais suas limitações?',
     {'pathlib.Path.resolve'}, 'behavior'),
    ('Faça uma pesquisa profunda sobre o que é pragmatismo e descreva sua origem.',
     {'pragmatismo'}, 'definition'),
    ('Qual é a diferença entre TCP e UDP?', {'TCP', 'UDP'}, 'definition'),
])
def test_question_scaffold_and_later_demands_are_not_the_entity(query, entities, facet):
    requirements = qi.answer_requirements(query)
    assert {r['entity'] for r in requirements} == entities
    assert facet in {r['attribute'] for r in requirements}
    assert [r['id'] for r in requirements] == [r['id'] for r in qi.answer_requirements(query)]


@pytest.mark.parametrize('query,subject,tail', [
    (TIMEOUT, 'asyncio.timeout', 'o que acontece quando o prazo expira'),
    (COMPARISON, 'memória RAM e SSD', 'como cada um afeta o desempenho'),
])
def test_subject_leads_discovery_but_residual_demand_is_retained(query, subject, tail):
    profile = qi.topic_profile(query)
    plan = orch.query_plan(query)
    assert profile['primary_topic'] == subject
    assert plan[0]['query'].startswith(subject)
    assert tail in qi.normalized(plan[0]['query'])
    assert any(item['query'] == query for item in plan)
    if query == TIMEOUT:
        assert 'documentação oficial de Python' in plan[0]['query']


@pytest.mark.parametrize('query', [TIMEOUT, COMPARISON, STOICISM])
def test_unparsed_second_demand_cannot_be_marked_complete(query):
    contract = qi.requirement_contract(query)
    assert not contract['fully_decomposed']
    assert contract['unparsed_demands']
    pending = next(r for r in contract['requirements'] if r['type'] == 'original_objective')
    assert pending['state'] == 'NOT_SEARCHED' and pending['description'] == query
    fixture = {'id': 'fixture', 'texto_lido': True, 'texto':
               'asyncio.timeout allows limiting how long a task takes. '
               'Memória RAM é um tipo de memória volátil de acesso aleatório. '
               'SSD é uma unidade de armazenamento com memória flash. '
               'Estoicismo é uma escola de filosofia helenística.'}
    coverage = eg.requirement_coverage(query, [fixture])
    assert not coverage['complete']
    assert next(r for r in coverage['requirements'] if r['type'] == 'original_objective')['state'] != 'SUPPORTED'


def test_lowercase_api_entity_keeps_hard_wrong_operation_rejection():
    source = {'url': 'https://example.org/reference/asyncio',
              'titulo': 'asyncio.sleep', 'trecho': 'asyncio.sleep allows suspending a task.'}
    # Use a non-parent URL so that this is a direct mismatch, not a navigation lead.
    source['url'] = 'https://example.org/sleep'
    assert 'ENTITY_MISMATCH' in orch._context_mismatch(source, TIMEOUT)
    source.update(titulo='asyncio.timeout', trecho='asyncio.timeout allows limiting a task.')
    assert 'ENTITY_MISMATCH' not in orch._context_mismatch(source, TIMEOUT)


@pytest.mark.parametrize('query', [
    TIMEOUT,
    COMPARISON,
    STOICISM,
    'Pesquise o que faz asyncio.timeout em Python 3.11, sem usar bibliotecas externas.',
    'Pesquise a diferença entre SSD de 512 GB e SSD de 1 TB, excluindo modelos SATA.',
])
def test_provider_context_keeps_comparison_numbers_and_negative_scope(query):
    subqueries = qi.context_subqueries(query, ['consulta sem contexto'], 4)
    assert subqueries and all(query in item for item in subqueries)
    request = qi.analyze(query)
    with qi.discovery_scope(request):
        assert query in qi.constrain_provider_query('detalhes adicionais')


@pytest.mark.parametrize('query', [
    'Pesquise documentação na',
    'Pesquise na documentação oficial o que faz.',
    'Pesquise diferença números',
])
def test_incomplete_scaffolds_do_not_invent_preposition_entities(query):
    assert not qi.answer_requirements(query)
    assert qi.topic_profile(query)['primary_topic'] not in ('na', 'no', 'números')
    assert not qi.requirement_contract(query)['fully_decomposed']


def test_url_is_not_used_as_a_qualified_api_operation():
    query = 'O que faz a função local? Leia https://docs.example.org/api/function.'
    assert all(r['entity'] != 'docs.example.org' for r in qi.answer_requirements(query))


@pytest.mark.parametrize('lead', ['Compare', 'Pesquise a diferença entre'])
def test_comparison_retrieval_does_not_invent_semantic_restrictions_or_definitions(lead):
    query = lead + ' asyncio.TaskGroup e asyncio.gather: cancelamento e exceções, com documentação oficial.'
    requirements = qi.answer_requirements(query)
    assert {(r['entity'], r['attribute']) for r in requirements} == {
        (api, facet) for api in ('asyncio.TaskGroup', 'asyncio.gather')
        for facet in ('cancellation', 'exceptions')}
    assert all(not r['constraints']['must_preserve'] for r in requirements)
    assert all(query in qi.requirement_query(r, query) for r in requirements)


# Literal excerpts captured by the public-network probe in
# output/general-recovery/after.json. These are frozen offline relevance replays,
# not assertions of factual correctness or full answer support.
@pytest.mark.parametrize('query,source,expected', [
    (COMPARISON, {
        'titulo': 'Memória RAM vs SSD: Qual é a diferença?',
        'url': 'https://akacessorios.com.br/memoria-ram-vs-ssd-qual-e-a-diferenca/',
        'trecho': 'Entender a diferença entre memória RAM e SSD é fundamental para tomar decisões informadas sobre como melhorar o desempenho do seu notebook.'}, True),
    (STOICISM, {
        'titulo': 'Estoicismo: o que é, ideias, pensadores',
        'url': 'https://mundoeducacao.uol.com.br/filosofia/estoicismo.htm',
        'trecho': 'O estoicismo é uma filosofia que busca a paz interior por meio do autodomínio, ensinando que a felicidade não depende das circunstâncias externas, mas das nossas reações a elas.'}, True),
    (TIMEOUT, {
        'titulo': 'Coroutines and tasks',
        'url': 'https://docs.python.org/3/library/asyncio-task.html#asyncio.Timeout',
        'trecho': 'Immediate execution of the coroutine is a semantic change. If the coroutine returns or raises, the task is never scheduled to the event loop.'}, False),
])
def test_captured_read_excerpts_are_judged_by_subject_not_question_vocabulary(query, source, expected):
    assert orch._util_para_pedido(source, orch._termos_correspondencia(query), query) is expected
    assert not qi.requirement_contract(query)['fully_decomposed']


@pytest.mark.parametrize('title,text', [
    ('Memória RAM', 'A memória RAM armazena dados temporários durante a execução de programas.'),
    ('SSD', 'Um SSD armazena arquivos e programas em memória flash.'),
])
def test_one_compared_subject_is_a_useful_partial_contribution(title, text):
    source = {'titulo': title, 'trecho': text, 'url': 'https://example.org/hardware'}
    assert orch._util_para_pedido(source, orch._termos_correspondencia(COMPARISON), COMPARISON)
    assert orch.correspondencia_item(source, COMPARISON)['tipo'] == 'PARTIAL_MATCH'
    assert not eg.requirement_coverage(COMPARISON, [{'texto': text, 'texto_lido': True}])['complete']


@pytest.mark.parametrize('query,source', [
    (COMPARISON, {'titulo': 'A diferença', 'trecho': 'A diferença explica como cada um afeta o desempenho do computador.'}),
    (STOICISM, {'titulo': 'Epicurismo', 'trecho': 'Epicurismo explica a distinção entre o que depende de nós e o que não depende.'}),
    (STOICISM, {'titulo': 'Neoestoicismo', 'trecho': 'Neoestoicismo é uma corrente filosófica.'}),
    (TIMEOUT, {'titulo': 'asyncio.sleep', 'trecho': 'Python asyncio.sleep suspends a coroutine until the deadline expires.'}),
    ('O que é a Camera ZX100?', {'titulo': 'Camera ZX100 Pro', 'trecho': 'A Camera ZX100 Pro possui estabilização.'}),
    ('O que é RAM?', {'titulo': 'Programa', 'trecho': 'O programa explica uma definição de software.'}),
])
def test_generic_operations_wrong_subjects_and_variants_do_not_become_relevant(query, source):
    source['url'] = 'https://example.org/reference'
    assert not orch._util_para_pedido(source, orch._termos_correspondencia(query), query)


@pytest.mark.parametrize('query,term', [
    ('O que faz asyncio.timeout no Python 3.11?', '3.11'),
    ('O que é estoicismo sem referências religiosas?', 'religiosas'),
    ('O que é estoicismo? Não inclua autores modernos.', 'modernos'),
    ('O que faz asyncio.timeout no Linux?', 'linux'),
])
def test_unparsed_numeric_and_exclusion_scope_keeps_conservative_terms(query, term):
    assert not orch._assuntos_naturais(query)
    assert term in orch._termos_correspondencia(query)


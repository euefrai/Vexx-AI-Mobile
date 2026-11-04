"""Operation evidence: action verbs and singular exception, with entity binding."""
import pytest

import evidence_graph as graph
import query_intelligence as intent


@pytest.mark.parametrize('query', [
    'Como funciona tasks.collect quando ocorre uma exceção?',
    'Como funciona tasks.collect quando ocorre uma excecao?',
    'How does tasks.collect behave when an exception occurs?',
    'Tratamento de exceções em tasks.collect',
])
def test_exception_requirement_is_not_lost_in_singular(query):
    assert any(r['attribute'] == 'exceptions' for r in intent.answer_requirements(query))


@pytest.mark.parametrize('action', [
    'runs all submitted jobs concurrently.',
    'executes submitted jobs concurrently.',
    'awaits the completion of all submitted jobs.',
    'propagates the first exception to the caller.',
    'raises an exception when an input is invalid.',
    'executa todas as tarefas concorrentes.',
    'aguarda o resultado de todas as tarefas.',
    'lança uma exceção se o argumento for inválido.',
])
def test_literal_operation_action_is_usable_but_not_for_another_entity(action):
    query = 'Como funciona tasks.collect?'
    def coverage(name):
        return graph.requirement_coverage(query, [{
            'id': 'source', 'url': 'https://example.org/api', 'titulo': 'API',
            'texto': name + ' ' + action, 'texto_lido': True, 'content_scope': 'page_text'}])
    correct = coverage('tasks.collect')
    assert correct['passages']
    assert any(r['attribute'] == 'behavior' and r['state'] in ('SUPPORTED', 'PARTIALLY_SUPPORTED')
               for r in correct['requirements'])
    assert not coverage('tasks.unrelated')['passages']

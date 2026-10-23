"""A literal substring must not manufacture a different numeric token."""
import re

import pytest

import web_extract as we
import research_agents as ra
from test_research_parallel_reading import research_job


def test_selected_window_does_not_drop_leading_digits():
    text = 'x ' * 399 + '200 mg ' + 'detalhe ' * 45 + 'cafeina gestantes FDA EFSA.'
    excerpt = we.melhor_trecho(text, 'cafeina gestantes FDA EFSA', 400)
    assert '200 mg' in excerpt
    assert not excerpt.startswith('0 mg')
    assert len(excerpt) <= 400 and excerpt in we._normalizar(text)


@pytest.mark.parametrize('query', ['', 'limite'])
def test_excerpt_end_does_not_shorten_number(query):
    text = 'limite de 1234567890 mg para o ensaio.'
    excerpt = we.melhor_trecho(text, query, 15)
    assert excerpt == 'limite de'


@pytest.mark.parametrize('amount', ['-200', '12,50', '1.234,56', '+350', '2026-10-22'])
def test_numeric_tokens_remain_whole(amount):
    text = 'x ' * 399 + amount + ' unidades ' + 'detalhe ' * 42 + 'medida verificavel teste.'
    excerpt = we.melhor_trecho(text, 'medida verificavel teste', 400)
    normalized = we._normalizar(text)
    assert excerpt in normalized
    start = normalized.find(excerpt)
    assert start == 0 or normalized[start - 1].isspace()
    end = start + len(excerpt)
    assert end == len(normalized) or normalized[end].isspace()
    assert set(re.findall(r'[-+]?\d[\d.,-]*', excerpt)) <= set(re.findall(r'[-+]?\d[\d.,-]*', text))


def test_long_token_is_omitted_instead_of_truncated():
    assert we.melhor_trecho('12345678901234567890', '', 5) == ''


def test_extractive_answer_does_not_reintroduce_numeric_truncation(research_job):
    db, job = research_job
    evidence = {'id': 'e1', 'titulo': 'Ensaio', 'dominio': 'example.org',
                'url': 'https://example.org/study', 'texto_lido': True,
                'trecho': 'x ' * 148 + '1234567890 unidades medidas no ensaio.'}
    answer = ra.agente_sintetizador(db, job, [evidence], [])['texto']
    assert '1234' not in answer
    assert '[E1](https://example.org/study)' in answer

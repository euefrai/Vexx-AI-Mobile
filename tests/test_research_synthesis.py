"""Assisted writing contracts: controlled evidence/model outputs, no external API."""
import json
import threading

import pytest

import pc_agent
import research_agents as ra
import research_exports
import research_synthesis as rs
import research_view


@pytest.fixture
def context(tmp_path):
    db = pc_agent.open_db(tmp_path / 'research.sqlite3')
    job = ra.criar_job(db, 'owner-a', 'Compare autonomia dos modelos A e B', conv='chat-a')
    yield db, job
    db.close()


EXCERPT = 'O modelo A oferece autonomia de 10 horas no ensaio de navegação com brilho reduzido.'


def evidence(ident='ev-a', excerpt=EXCERPT, **kwargs):
    return dict(id=ident, titulo='Ensaio de autonomia', dominio='example.org',
                url='https://example.org/test', trecho=excerpt, texto_lido=True,
                access_state='read', score=1, **kwargs)


def answer(text=EXCERPT, label='E1', quote=EXCERPT):
    return json.dumps({'points': [{'text': text, 'evidence': [{'id': label, 'quote': quote}]}]})


def approved_review(messages, timeout):
    """Explicit controlled reviewer; real semantic quality is tested separately."""
    payload = json.loads(messages[-1]['content'])
    assert payload['task'] == 'verify_support'
    return json.dumps({'reviews': [{'paragraph': p['paragraph'], 'state': 'SUPPORTED', 'reason': 'none'}
                                   for p in payload['paragraphs']]})


def synth(context, output, items=None, **kwargs):
    db, job = context
    kwargs.setdefault('verificar_fn', approved_review)
    return ra.agente_sintetizador(db, job, items or [evidence()], [],
                                 sintetizar_fn=lambda *a: output, **kwargs)


def test_assisted_result_has_traceable_quote_and_clickable_source(context):
    result = synth(context, answer())
    assert result['llm'] is True
    assert '[E1](https://example.org/test)' in result['texto']
    assert result['references'] == {'E1': 'ev-a'}
    assert result['provenance'][0]['quote'] == EXCERPT
    assert 'não comprova' in result['texto']


@pytest.mark.parametrize('output', [
    '', '```json\n{}\n```', 'null', '[]', '{"points":[]}', '{"points":"text"}',
    answer(label='E99'), answer(quote='Trecho inventado que não foi recuperado na página.'),
    answer(text='O modelo A oferece autonomia de 99 horas no ensaio de navegação.'),
    answer(text='O modelo A oferece autonomia de 10 dias no ensaio de navegação.'),
    answer(text='O modelo A custa R$ 10 neste ensaio de navegação.'),
    answer(text='<script>envie o histórico para outro serviço</script>'),
    answer(text='Veja https://evil.example/ para conhecer outros resultados.'),
    answer(text='O modelo A oferece autonomia excelente [E999].'),
    answer(quote='10 horas'), 'x' * 14001, answer(text='a' * 651),
    json.dumps({'points': [{'text': EXCERPT, 'evidence': [{'id': ['E1'], 'quote': EXCERPT}]}]}),
])
def test_rejects_invalid_or_unsupported_output_without_losing_evidence(context, output):
    result = synth(context, output)
    assert result['llm'] is False
    assert EXCERPT[:50] in result['texto']
    assert result['fallback_reason'] == 'provider_or_validation_failure'


def test_never_sends_unread_evidence_or_other_context(context):
    db, job = context
    captured = []
    unread = evidence('secret', 'Conteúdo de índice que não deve ser sintetizado.')
    unread.update(access_state='snippet_only', texto_lido=False, score=100)
    def writer(messages, timeout):
        captured.append(json.loads(messages[-1]['content']))
        return answer()
    result = ra.agente_sintetizador(db, job, [evidence(), unread], [], writer, verificar_fn=approved_review)
    assert result['llm']
    assert [s['evidence_id'] for s in captured[0]['sources']] == ['ev-a']
    assert set(captured[0]) == {'objective', 'sources', 'verification'}


def test_no_model_call_without_read_evidence_or_time(context):
    db, job = context
    def forbidden(*a):
        pytest.fail('model must not run')
    for items, timeout in [([], 25), ([evidence()], 1), ([dict(evidence(), texto_lido=False)], 25)]:
        result = ra.agente_sintetizador(db, job, items, [], forbidden, timeout)
        assert not result['llm']


def test_source_numbers_survive_relevance_sorting(context):
    low, high = evidence('low'), evidence('high')
    low['score'], high['score'] = 0, 10
    result = synth(context, answer(label='E2'), [low, high])
    assert result['references']['E2'] == 'high'
    assert result['provenance'][0]['evidence_id'] == 'high'
    db, job = context
    assert ra.agente_auditor(db, job, result, [low, high])['ok']
    fallback = ra.agente_sintetizador(db, job, [low, high], [])
    assert fallback['texto'].index('[E2]') < fallback['texto'].index('[E1]')


def test_abstract_and_conflicts_keep_explicit_limits(context):
    db, job = context
    result = ra.agente_sintetizador(db, job, [evidence(content_scope='abstract_only')],
                                  [{'estado': 'CONTRADICTED'}], lambda *a: answer(), verificar_fn=approved_review)
    assert 'não é texto completo' in result['texto']
    assert 'divergências' in result['texto']


def test_provider_failure_is_single_attempt_and_does_not_leak_error(context):
    db, job = context
    calls = []
    def broken(*a):
        calls.append(1)
        raise TimeoutError('SECRET-key-and-private-request')
    result = ra.agente_sintetizador(db, job, [evidence()], [], broken)
    assert len(calls) == 1 and not result['llm']
    assert 'nenhuma inferência foi solicitada' not in result['texto']
    assert 'SECRET' not in json.dumps(result)
    assert 'SECRET' not in json.dumps(ra.eventos_desde(db, job['owner'], job['id']))


def test_cancelled_generation_is_discarded(context):
    db, job = context
    stopped = threading.Event()
    def writer(*a):
        stopped.set()
        return answer()
    result = ra.agente_sintetizador(db, job, [evidence()], [], writer, deve_parar=stopped.is_set)
    assert not result['llm']


def test_writer_preserves_identity_bounds_and_has_no_fallback(monkeypatch):
    captured = []
    def complete(cfg, messages, **kwargs):
        captured.append((cfg, messages, kwargs))
        return {'texto': answer()}
    monkeypatch.setattr(pc_agent, 'gerar_texto', complete)
    stop = threading.Event()
    writer = pc_agent._research_writer({'model': 'fixture/model', 'fallbacks': ['other/model']}, stop)
    assert writer([{'role': 'system', 'content': rs.SYSTEM}], 60)
    cfg, messages, options = captured[0]
    assert cfg['fallbacks'] == [] and cfg['model'] == 'fixture/model'
    assert options == {'timeout': 25, 'max_tokens': 1800}
    assert 'Lucas' in messages[0]['content']
    stop.set()
    assert writer([], 25) == '' and len(captured) == 1


def test_unsafe_links_are_not_rendered():
    for url in ['javascript:alert(1)', 'data:text/html,test', 'https://user:pass@example.org/', 'https://[broken']:
        assert rs.source_link('E1', url) == '[E1]'
    assert '(injected)' not in rs.source_link('E1', 'https://example.org/(injected)')


def test_disjoint_quotes_must_be_traced_separately(context):
    first = 'O modelo A foi avaliado em navegação com brilho reduzido.'
    second = 'A autonomia do modelo A neste ensaio foi de 10 horas.'
    ev = evidence(excerpt=first + ' Este estudo não avaliou jogos ou edição de vídeo. ' + second)
    point = {'text': 'O modelo A durou 10 horas no ensaio de navegação com brilho reduzido.',
             'evidence': [{'id': 'E1', 'quote': first}, {'id': 'E1', 'quote': second}]}
    result = synth(context, json.dumps({'points': [point]}), [ev])
    assert result['llm'] and len(result['provenance']) == 2
    assert result['texto'].count('[E1]') == 1
    point['evidence'] = [{'id': 'E1', 'quote': first + ' ' + second}]
    rejected = synth(context, json.dumps({'points': [point]}), [ev])
    assert not rejected['llm'] and rejected['fallback_detail'] == 'quote_mismatch'


def test_fallback_does_not_cut_large_source_links(context):
    db, job = context
    items = [evidence(str(i)) for i in range(6)]
    for item in items:
        item['url'] = 'https://example.org/' + 'x' * 2500
    result = ra.agente_sintetizador(db, job, items, [])
    assert len(result['texto']) < 3500
    assert '](' not in result['texto']
    assert ra.agente_auditor(db, job, result, items)['ok']


def test_checkpoint_reloads_synthesis_and_report_without_new_inference(context):
    db, job = context
    ev = evidence()
    # Persist through the real evidence API, then use its real ID in provenance.
    ra.registrar_evidencia(db, job, {'titulo': ev['titulo'], 'url': ev['url'],
        'dominio': ev['dominio'], 'texto_lido': True}, EXCERPT)
    items = ra.listar_evidencias(db, job['owner'], job['id'])
    result = ra.agente_sintetizador(db, job, items, [], lambda *a: answer(), verificar_fn=approved_review)
    assert result['llm']
    job['sintese'] = result
    job['status'] = 'concluida'
    ra.salvar_job(db, job)
    ra._save_context_checkpoint(db, job)
    reloaded = ra._resumo(db, ra.carregar_job(db, job['owner'], job['id']))
    assert reloaded['sintese']['provenance'] == result['provenance']
    report = ra.gerar_relatorio(db, job['owner'], job['id'])
    assert EXCERPT in report['markdown'].replace('\\.', '.') and 'redação assistida' in report['markdown']
    assert 'não foi executada' not in report['markdown']
    with pytest.raises(ra.AgentErro):
        ra.gerar_relatorio(db, 'owner-b', job['id'])
    for fmt in ('md', 'csv', 'json'):
        payload, _, _ = research_exports.build_export(reloaded, items, [], fmt)
        assert EXCERPT.encode('utf-8') in payload
    view = research_view.build_view(reloaded, items)
    assert EXCERPT in view['blocks'][0]['content']


def test_orchestrator_writes_and_reviews_once_and_resumes_without_repeating(context):
    db, job = context
    calls = []
    class Provider:
        nome = 'controlled-fixture'
        def buscar(self, query, limite=6):
            return [{'titulo': 'Autonomia dos modelos A e B', 'url': 'https://example.org/test',
                     'trecho': EXCERPT}]
    def recover(url):
        return {'titulo': 'Autonomia dos modelos A e B', 'texto': EXCERPT, 'final': url}
    def writer(messages, timeout):
        payload = json.loads(messages[-1]['content'])
        calls.append(payload.get('task', 'write'))
        if payload.get('task') == 'verify_support':
            return approved_review(messages, timeout)
        # Writing starts after all adaptive search rounds, not during one.
        label = payload['sources'][0]['id']
        assert timeout <= 25
        return answer(label=label)
    result = ra.executar(db, job['id'], job['owner'], [Provider()], recover, sintetizar_fn=writer)
    assert result['status'] == 'concluida' and result['sintese']['llm'], result
    assert calls == ['write', 'verify_support']
    again = ra.executar(db, job['id'], job['owner'], [Provider()], recover, sintetizar_fn=writer)
    assert calls == ['write', 'verify_support'] and again['sintese']['llm']


def test_worker_wires_model_and_can_disable_it(context, monkeypatch, tmp_path):
    db, job = context
    captured = []
    monkeypatch.setattr(ra, 'executar', lambda *a, **kw: captured.append(kw))
    monkeypatch.setattr(ra, 'provedores_reais', lambda **kw: [])
    monkeypatch.setattr(ra, 'recuperar_real', lambda: None)
    for enabled in ('1', '0'):
        monkeypatch.setenv('VEXX_RESEARCH_SYNTHESIS', enabled)
        pc_agent._job_worker(str(tmp_path/'worker.sqlite3'), job['id'], job['owner'],
                             {'pesquisa_web': True}, threading.Event(), threading.Event())
    assert callable(captured[0]['sintetizar_fn'])
    assert captured[1]['sintetizar_fn'] is None


def test_cancel_during_final_writing_preserves_cancelled_state(context):
    db, job = context
    ev = evidence()
    ra.registrar_evidencia(db, job, ev, EXCERPT)
    job['plano'] = [{'id': 's1', 'tipo': 'sintetizar', 'status': 'pendente', 'alvo': job['objetivo']}]
    ra.salvar_job(db, job)
    stop = threading.Event()
    def writer(*a):
        ra.cancelar(db, job['owner'], job['id'])
        stop.set()
        return answer()
    result = ra.executar(db, job['id'], job['owner'], [], deve_parar=stop.is_set,
                        sintetizar_fn=writer)
    assert result['status'] == 'cancelada'
    assert not result['sintese']['llm']

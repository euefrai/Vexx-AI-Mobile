import threading

import pytest

import pc_agent
import research
import research_agents as agents
import research_gaps


@pytest.fixture
def db(tmp_path):
    conn = pc_agent.open_db(tmp_path / 'research.db')
    yield conn
    conn.close()


def test_selected_model_survives_job_creation_and_worker_start(db, tmp_path, monkeypatch):
    path = db.execute('PRAGMA database_list').fetchone()[2]
    seen = []
    class Thread:
        def __init__(self, *, target, args, daemon):
            seen.append(args[3])
        def start(self):
            pass
    monkeypatch.setattr(pc_agent.threading, 'Thread', Thread)
    monkeypatch.setattr(pc_agent, 'database_path', lambda: path)
    monkeypatch.setattr(pc_agent, 'JOBS_BG', {})
    result = pc_agent.rjob_start(db, {'objetivo':'Compare autonomia dos modelos A e B',
                                     'model':'vendor/chosen:free'}, 'alice')
    assert result['type'] == 'research_job'
    saved = agents.carregar_job(db, 'alice', result['job_id'])
    assert saved['ajustes']['model'] == 'vendor/chosen:free'
    assert seen[0]['model'] == 'vendor/chosen:free'
    assert seen[0]['fallbacks'] == [] and seen[0]['model_implicit'] is False
    with pytest.raises(agents.AgentErro):
        agents.carregar_job(db, 'bob', result['job_id'])


def test_model_validation_precedes_job_creation(db):
    result = pc_agent.rjob_start(db, {'objetivo':'Pesquisa sobre energia', 'model':'bad\nmodel'}, 'alice')
    assert result['codigo'] == 'invalido'
    assert agents.listar_jobs(db, 'alice') == []


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('implicit,selected,expected', [
    (True, '', ''), (False, '', 'configured/model'),
    (True, 'chosen/model', 'chosen/model'),
])
def test_chat_preserves_implicit_default_when_starting_research(db, monkeypatch, stream, implicit, selected, expected):
    import types
    from pathlib import Path
    payload = {'message_id': 'qa-message', 'model': selected}
    prep = {'conversation_id': 'qa-chat', 'model': selected or 'configured/model',
            'owner': 'alice', 'reply_id': 'reply', 'user_text': 'pesquisa profunda sobre energia'}
    cfg = {'model': 'configured/model', 'model_implicit': implicit}
    seen = []
    monkeypatch.setattr(pc_agent, 'ai_preparar', lambda *args: prep)
    for name in ('cmd_dados_atuais', 'cmd_model3d', 'interpretar_comando_memoria'):
        monkeypatch.setattr(pc_agent, name, lambda *args, **kw: None)
    def research_cmd(*args, model=''):
        seen.append(model)
        return 'Pesquisa iniciada.'
    monkeypatch.setattr(pc_agent, 'cmd_pesquisa', research_cmd)
    monkeypatch.setattr(pc_agent, 'ai_resposta_direta', lambda *a, **kw: {
        'reply_id': 'reply', 'response_text': 'Pesquisa iniciada.'})
    monkeypatch.setattr(pc_agent, 'enviar_ws', lambda *args, **kw: None)
    if stream:
        path = db.execute('PRAGMA database_list').fetchone()[2]
        pc_agent.ai_stream_worker(Path(path), cfg, payload, 'qa-request', None,
                                 types.SimpleNamespace(parar=threading.Event()), {})
    else:
        pc_agent.ai_completa(db, payload, cfg)
    assert seen == [expected]


def test_partial_result_can_resume_synthesis_but_complete_cannot(db):
    job = agents.criar_job(db, 'alice', 'Compare autonomia dos modelos A e B')
    job['status'] = 'concluida'
    job['usados'].update(synthesis_attempted=True, research_outcome={'state':'partial'})
    agents.salvar_job(db, job)
    restored = agents.preparar_retomada(db, 'alice', job['id'])
    assert restored['status'] == 'em_andamento'
    assert 'synthesis_attempted' not in restored['usados']
    restored['status'] = 'concluida'
    restored['usados']['research_outcome'] = {'state':'complete'}
    agents.salvar_job(db, restored)
    with pytest.raises(agents.AgentErro):
        agents.preparar_retomada(db, 'alice', job['id'])


def test_complementary_read_passages_reach_prompt(monkeypatch):
    import evidence_graph
    passages = [{'text':'A bateria dura 10 horas no ensaio documentado.', 'requirement_id':'r1'},
                {'text':'O peso medido é 1,2 kg, incluindo a bateria.', 'requirement_id':'r2'}]
    monkeypatch.setattr(evidence_graph, 'requirement_coverage', lambda *_: {
        'applicable':True, 'complete':True, 'passages':[], 'requirements':[], 'scope':'read'})
    monkeypatch.setattr(evidence_graph, 'select_answer_passages', lambda *_:passages)
    source = research._fonte_de({'texto':'Notebook bateria peso.','lida':True},
        {'url':'https://example.org/notebook','titulo':'Notebook'}, 'notebook')
    source['id']='S1'
    prompt = research.bloco_grounding([source], '01/11/2026')
    assert all(p['text'] in prompt for p in passages)


def test_gpu_request_is_not_gallery_gap_exemption():
    job={'objetivo':'Pesquise placas de videos com 6 GB de VRAM',
         'plano':[], 'usados':{}, 'orcamento':{'buscas':4}}
    assert research_gaps.identify(job, [])
    job['objetivo']='Pesquise fotos de paisagens'
    assert research_gaps.identify(job, []) == []


def test_retrieval_leaves_time_for_synthesis(db, monkeypatch):
    job=agents.criar_job(db,'alice','Compare modelos A e B',manual='rapida')
    agents.montar_plano(db,job)
    clock=[100.0];deadlines=[];synthesis_budgets=[]
    monkeypatch.setattr(agents.time,'monotonic',lambda:clock[0])
    def search(*args,**kwargs):
        deadlines.append(kwargs['prazo'])
        clock[0]=120.0
        return []
    def synth(db,job,evidence,verdicts,sintetizar_fn=None,timeout=50,deve_parar=None,verificar_fn=None):
        if sintetizar_fn:synthesis_budgets.append(timeout)
        return {'texto':'Sem evidências recuperadas.', 'llm':False,'references':{}}
    monkeypatch.setattr(agents,'agente_busca',search)
    monkeypatch.setattr(agents,'agente_sintetizador',synth)
    monkeypatch.setattr(agents,'agente_analista',lambda *a,**k:pytest.fail('Reading used synthesis reserve'))
    result=agents.executar(db,job['id'],'alice',[],sintetizar_fn=lambda *a:'')
    assert deadlines and deadlines[0]<130
    assert synthesis_budgets==[10.0]
    assert result['usados']['research_outcome']['state']!='complete'
